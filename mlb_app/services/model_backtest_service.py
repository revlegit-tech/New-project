from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.data_source_capability_service import resolve_date_mode
from mlb_app.services.model_calibration_service import _baseline_model_exists, _probability_rows
from mlb_app.services.runtime_status_service import safe_relpath

SCHEMA_VERSION = "model-backtest-status.v1"
MIN_BACKTEST_ROWS = 200


class ModelBacktestService:
    """Inspect and optionally write evaluation-only baseline backtest artifacts."""

    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def status(self, *, date_label: str | None, season: int | None, market: str) -> dict[str, Any]:
        target_date, _ = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        selected_market = _safe_market(market)
        artifact_path = self.artifact_dir(selected_market) / "backtest_metrics.json"
        metrics = _read_json(artifact_path)
        artifact_exists = artifact_path.is_file()
        warnings = []
        if not artifact_exists:
            warnings.append("Backtest artifact is missing for this market.")
        return {
            "schemaVersion": SCHEMA_VERSION,
            "date": target_date,
            "season": selected_season,
            "market": selected_market,
            "artifactExists": artifact_exists,
            "backtestStatus": _status_from_metrics(metrics, artifact_exists),
            "metrics": metrics if isinstance(metrics, dict) else {},
            "modelTrainingTriggered": False,
            "externalApiCallsMade": False,
            "warnings": warnings,
        }

    def backtest(
        self,
        *,
        date_label: str | None,
        season: int | None,
        market: str,
        backtest: bool = False,
    ) -> dict[str, Any]:
        target_date, mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        selected_market = _safe_market(market)
        artifact_dir = self.artifact_dir(selected_market)
        model_exists = _baseline_model_exists(artifact_dir)
        rows = _probability_rows(self._label_files(selected_season), selected_market)
        warnings: list[str] = []
        if not model_exists:
            warnings.append("Baseline model artifact is missing for this market.")
        if not rows:
            warnings.append("No labels with probability estimates were found for backtesting.")
        if len(rows) and len(rows) < MIN_BACKTEST_ROWS:
            warnings.append(f"Backtest sample size is low: {len(rows)} < {MIN_BACKTEST_ROWS}.")

        metrics: dict[str, Any] = {}
        bucket_rows: list[dict[str, Any]] = []
        status = "missing"
        artifact_written = False
        if model_exists and rows:
            metrics, bucket_rows = _backtest_metrics(rows)
            status = "ready" if len(rows) >= MIN_BACKTEST_ROWS else "low_sample"
            if backtest:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                _write_json(artifact_dir / "backtest_metrics.json", metrics)
                _write_buckets(artifact_dir / "backtest_by_bucket.csv", bucket_rows)
                _write_json(
                    artifact_dir / "backtest_manifest.json",
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        "generatedAt": datetime.now(timezone.utc).isoformat(),
                        "date": target_date,
                        "season": selected_season,
                        "market": selected_market,
                        "evaluatedRows": metrics.get("evaluatedRows", 0),
                        "backtestStatus": status,
                    },
                )
                artifact_written = True

        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok",
            "date": target_date,
            "season": selected_season,
            "resolvedDateMode": mode,
            "market": selected_market,
            "dryRun": not backtest,
            "backtestRequested": backtest,
            "artifactDir": safe_relpath(artifact_dir, self.settings.root_dir),
            "artifactExists": (artifact_dir / "backtest_metrics.json").is_file(),
            "artifactWritten": artifact_written,
            "backtestStatus": status,
            "metrics": metrics,
            "modelTrainingTriggered": False,
            "externalApiCallsMade": False,
            "warnings": _dedupe(warnings),
        }

    def artifact_dir(self, market: str) -> Path:
        return self.settings.data_dir / "models" / "baseline" / _safe_market(market)

    def _label_files(self, season: int) -> list[Path]:
        candidates = [
            self.settings.data_dir / "labels" / f"player_prop_labels_{season}.csv",
            self.settings.data_dir / "training" / f"player_prop_labels_{season}.csv",
        ]
        return [path for path in candidates if path.is_file()]


def _backtest_metrics(rows: list[dict[str, float]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    count = len(rows)
    hit_rate = sum(row["target"] for row in rows) / count
    avg_probability = sum(row["probability"] for row in rows) / count
    average_edge = avg_probability - hit_rate
    buckets: list[dict[str, Any]] = []
    for low, high in ((0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.01)):
        bucket_rows = [row for row in rows if low <= row["probability"] < high]
        if not bucket_rows:
            continue
        bucket_count = len(bucket_rows)
        buckets.append(
            {
                "bucket": f"{low:.2f}-{min(high, 1.0):.2f}",
                "evaluatedRows": bucket_count,
                "hitRate": sum(row["target"] for row in bucket_rows) / bucket_count,
                "precision": sum(row["target"] for row in bucket_rows if row["probability"] >= 0.5)
                / max(1, sum(1 for row in bucket_rows if row["probability"] >= 0.5)),
                "roi": None,
                "clv": None,
            }
        )
    return {
        "evaluatedRows": count,
        "coverage": 1.0,
        "hitRate": hit_rate,
        "averageProbability": avg_probability,
        "averageEdge": average_edge,
        "hasOdds": False,
        "hasClv": False,
    }, buckets


def _status_from_metrics(metrics: dict[str, Any], artifact_exists: bool) -> str:
    if not artifact_exists:
        return "missing"
    if int(metrics.get("evaluatedRows") or 0) < MIN_BACKTEST_ROWS:
        return "low_sample"
    return "ready"


def _write_buckets(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["bucket", "evaluatedRows", "hitRate", "precision", "roi", "clv"])
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _safe_market(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(value or "").strip()) or "unknown"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
