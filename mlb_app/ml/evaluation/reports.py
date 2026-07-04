from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.ml.evaluation.walk_forward import evaluate_training_rows_by_market, evaluate_walk_forward


def evaluate_csv(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    target = Path(path)
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    probability_field = str(kwargs.pop("probability_field", "model_probability"))
    artifact_root = kwargs.pop("artifact_root", None)
    write_artifacts = bool(kwargs.pop("write_artifacts", False))
    markets = kwargs.pop("markets", None)
    has_probability = any(str(row.get(probability_field) or "").strip() for row in rows)
    if has_probability:
        return evaluate_walk_forward(rows, probability_field=probability_field, **kwargs)

    report = evaluate_training_rows_by_market(rows, markets=markets, **kwargs)
    if write_artifacts and artifact_root:
        written = write_shadow_artifacts(artifact_root, report, source_path=target)
        report["artifactWrites"] = written
    return report


def write_report(path: str | Path, report: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_shadow_artifacts(path: str | Path, report: dict[str, Any], *, source_path: Path) -> list[dict[str, Any]]:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    writes: list[dict[str, Any]] = []
    for market, market_report in sorted((report.get("markets") or {}).items()):
        market_dir = root / _safe_market(str(market))
        market_dir.mkdir(parents=True, exist_ok=True)
        metrics = dict(market_report.get("metrics") or {})
        calibration = dict(market_report.get("calibration") or {})
        common = {
            "generatedAt": generated_at,
            "sourcePath": str(source_path),
            "market": str(market),
            "modelStage": "shadow",
            "modelKey": "calibrated_logistic",
            "readinessLabel": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "betActionAllowed": False,
        }
        backtest_payload = {
            **common,
            "schemaVersion": "sprint19-shadow-backtest.v1",
            "evaluatedRows": metrics.get("evaluatedRows", 0),
            "brierScore": metrics.get("brierScore"),
            "logLoss": metrics.get("logLoss"),
            "auc": metrics.get("auc"),
            "positiveRows": metrics.get("positiveRows", 0),
            "negativeRows": metrics.get("negativeRows", 0),
            "validationDates": metrics.get("validationDates") or [],
            "splitCount": metrics.get("splitCount", 0),
            "warnings": metrics.get("warnings") or [],
        }
        calibration_payload = {
            **common,
            "schemaVersion": "sprint19-shadow-calibration.v1",
            "sampleCount": calibration.get("sampleCount", 0),
            "brierScore": calibration.get("brierScore"),
            "logLoss": calibration.get("logLoss"),
            "expectedCalibrationError": calibration.get("expectedCalibrationError"),
            "bucketCount": calibration.get("bucketCount", 0),
            "buckets": calibration.get("buckets") or [],
        }
        write_report(market_dir / "backtest_metrics.json", backtest_payload)
        write_report(market_dir / "calibration.json", calibration_payload)
        write_report(
            market_dir / "shadow_manifest.json",
            {
                **common,
                "schemaVersion": "sprint19-shadow-manifest.v1",
                "backtestStatus": "ready" if int(metrics.get("evaluatedRows") or 0) else "missing",
                "calibrationStatus": "ready" if int(calibration.get("sampleCount") or 0) else "missing",
            },
        )
        writes.append(
            {
                "market": str(market),
                "artifactDir": str(market_dir),
                "backtestMetrics": str(market_dir / "backtest_metrics.json"),
                "calibration": str(market_dir / "calibration.json"),
            }
        )
    return writes


def _safe_market(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(value or "").strip()) or "unknown"
