from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.feature_store_schema import postgame_label_names, pregame_feature_names
from mlb_app.services.data_source_capability_service import resolve_date_mode
from mlb_app.services.runtime_status_service import safe_relpath

SCHEMA_VERSION = "model-calibration-status.v1"
MIN_CALIBRATION_ROWS = 200


class ModelCalibrationService:
    """Inspect and optionally write baseline calibration artifacts."""

    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def status(self, *, date_label: str | None, season: int | None, market: str) -> dict[str, Any]:
        target_date, _ = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        selected_market = _safe_market(market)
        artifact_path = self.artifact_dir(selected_market) / "calibration.json"
        metrics = _read_json(artifact_path)
        artifact_exists = artifact_path.is_file()
        warnings = []
        if not artifact_exists:
            warnings.append("Calibration artifact is missing for this market.")
        return {
            "schemaVersion": SCHEMA_VERSION,
            "date": target_date,
            "season": selected_season,
            "market": selected_market,
            "artifactExists": artifact_exists,
            "calibrationStatus": _status_from_metrics(metrics, artifact_exists),
            "metrics": metrics if isinstance(metrics, dict) else {},
            "modelTrainingTriggered": False,
            "externalApiCallsMade": False,
            "warnings": warnings,
        }

    def calibrate(
        self,
        *,
        date_label: str | None,
        season: int | None,
        market: str,
        calibrate: bool = False,
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
        if not rows and model_exists:
            scored = _baseline_model_probability_rows(
                settings=self.settings,
                artifact_dir=artifact_dir,
                date_label=target_date,
                season=selected_season,
                market=selected_market,
            )
            rows = scored["rows"]
            warnings.extend(scored["warnings"])
        if not rows:
            warnings.append("No labels with probability estimates were found for calibration.")
        if len(rows) and len(rows) < MIN_CALIBRATION_ROWS:
            warnings.append(f"Calibration sample size is low: {len(rows)} < {MIN_CALIBRATION_ROWS}.")

        metrics: dict[str, Any] = {}
        curve: list[dict[str, Any]] = []
        status = "missing"
        artifact_written = False
        if model_exists and rows:
            metrics, curve = _calibration_metrics(rows)
            status = "ready" if len(rows) >= MIN_CALIBRATION_ROWS else "low_sample"
            if calibrate:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                _write_json(artifact_dir / "calibration.json", metrics)
                _write_curve(artifact_dir / "reliability_curve.csv", curve)
                _write_json(
                    artifact_dir / "calibration_manifest.json",
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        "generatedAt": datetime.now(timezone.utc).isoformat(),
                        "date": target_date,
                        "season": selected_season,
                        "market": selected_market,
                        "sampleCount": metrics.get("sampleCount", 0),
                        "calibrationStatus": status,
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
            "dryRun": not calibrate,
            "calibrateRequested": calibrate,
            "artifactDir": safe_relpath(artifact_dir, self.settings.root_dir),
            "artifactExists": (artifact_dir / "calibration.json").is_file(),
            "artifactWritten": artifact_written,
            "calibrationStatus": status,
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


def _calibration_metrics(rows: list[dict[str, float]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    count = len(rows)
    brier = sum((row["probability"] - row["target"]) ** 2 for row in rows) / count
    log_loss = -sum(
        row["target"] * _safe_log(row["probability"]) + (1 - row["target"]) * _safe_log(1 - row["probability"])
        for row in rows
    ) / count
    buckets = _bucket_rows(rows, probability_key="probability")
    ece = sum((bucket["count"] / count) * abs(bucket["averageProbability"] - bucket["observedRate"]) for bucket in buckets)
    metrics = {
        "sampleCount": count,
        "brierScore": brier,
        "logLoss": log_loss,
        "expectedCalibrationError": ece,
        "bucketCount": len(buckets),
    }
    return metrics, buckets


def _bucket_rows(rows: list[dict[str, float]], *, probability_key: str) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for index in range(10):
        low = index / 10
        high = (index + 1) / 10
        bucket_rows = [row for row in rows if low <= row[probability_key] < high or (index == 9 and row[probability_key] == 1.0)]
        if not bucket_rows:
            continue
        count = len(bucket_rows)
        buckets.append(
            {
                "bucket": f"{low:.1f}-{high:.1f}",
                "count": count,
                "averageProbability": sum(row[probability_key] for row in bucket_rows) / count,
                "observedRate": sum(row["target"] for row in bucket_rows) / count,
            }
        )
    return buckets


def _probability_rows(files: list[Path], market: str) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for path in files:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if _clean(row.get("market") or row.get("baseMarket") or row.get("prop_market")) != market:
                        continue
                    target = _target(row)
                    probability = _probability(row)
                    if target is None or probability is None:
                        continue
                    rows.append({"target": float(target), "probability": probability})
        except OSError:
            continue
    return rows


def _baseline_model_probability_rows(
    *,
    settings: Settings,
    artifact_dir: Path,
    date_label: str,
    season: int,
    market: str,
    purpose: str = "calibration",
) -> dict[str, Any]:
    from mlb_app.services.baseline_model_training_service import BaselineModelTrainingService

    warnings: list[str] = []
    feature_columns_path = artifact_dir / "feature_columns.json"
    model_path = artifact_dir / "model.joblib"
    if not model_path.is_file():
        warnings.append("Baseline model artifact is missing for this market.")
        return {"rows": [], "warnings": warnings}
    feature_columns = _feature_columns_manifest(feature_columns_path)
    if not feature_columns:
        warnings.append("Feature columns manifest is missing or invalid for this market.")
        return {"rows": [], "warnings": warnings}
    blocked = sorted(set(feature_columns).intersection(postgame_label_names()))
    allowed = set(pregame_feature_names())
    non_pregame = sorted(column for column in feature_columns if column not in allowed)
    if blocked or non_pregame:
        warnings.append("Feature columns manifest contains non-pregame or postgame label fields.")
        return {"rows": [], "warnings": warnings}

    joined = BaselineModelTrainingService(settings)._joined_rows(
        target_date=date_label,
        season=season,
        market=market,
        label_files=_readiness_label_artifacts(settings=settings, date_label=date_label, season=season, market=market),
    )
    if not joined:
        warnings.append(f"No joined feature rows with labels were found for {purpose}.")
        return {"rows": [], "warnings": warnings}

    try:
        import joblib
        import numpy as np

        model = joblib.load(model_path)
        matrix = np.asarray([[_float_for_model(row.get(column)) for column in feature_columns] for row in joined], dtype=float)
        probabilities = model.predict_proba(matrix)[:, 1]
    except Exception as exc:
        warnings.append(f"Baseline model scoring failed for {purpose}: {exc}")
        return {"rows": [], "warnings": warnings}

    rows = [
        {"target": float(row["__target"]), "probability": max(0.0, min(1.0, float(probability)))}
        for row, probability in zip(joined, probabilities, strict=False)
    ]
    return {"rows": rows, "warnings": warnings}


def _feature_columns_manifest(path: Path) -> list[str]:
    payload = _read_json_or_list(path)
    if isinstance(payload, list):
        return [_clean(item) for item in payload if _clean(item)]
    if isinstance(payload, dict):
        columns = payload.get("featureColumns") or payload.get("feature_columns") or payload.get("columns")
        if isinstance(columns, list):
            return [_clean(item) for item in columns if _clean(item)]
    return []


def _readiness_label_artifacts(*, settings: Settings, date_label: str, season: int, market: str) -> list[str]:
    from mlb_app.services.baseline_model_training_service import BaselineModelTrainingService

    artifacts: list[str] = []
    try:
        readiness = BaselineModelTrainingService(settings).readiness.payload(date_label=date_label, season=season, market=market)
        artifacts.extend(str(path) for path in readiness.get("labelArtifacts") or [])
    except Exception:
        pass
    warehouse_csv = settings.data_dir / "warehouse" / "ml_labels" / f"player_prop_labels_{date_label}.csv"
    if warehouse_csv.is_file():
        artifacts.append(safe_relpath(warehouse_csv, settings.root_dir))
    return _dedupe(artifacts)


def _baseline_model_exists(artifact_dir: Path) -> bool:
    return (artifact_dir / "model.joblib").is_file() or (artifact_dir / "model.pkl").is_file()


def _status_from_metrics(metrics: dict[str, Any], artifact_exists: bool) -> str:
    if not artifact_exists:
        return "missing"
    if int(metrics.get("sampleCount") or 0) < MIN_CALIBRATION_ROWS:
        return "low_sample"
    return "ready"


def _target(row: dict[str, Any]) -> int | None:
    result = _clean(row.get("result") or row.get("target_result") or row.get("outcome")).lower()
    hit = _clean(row.get("hit") if "hit" in row else row.get("target_hit")).lower()
    if hit in {"1", "true", "yes", "hit", "win", "won"} or result in {"hit", "win", "won", "over"}:
        return 1
    if hit in {"0", "false", "no", "miss", "loss", "lost"} or result in {"miss", "loss", "lost", "under"}:
        return 0
    return None


def _probability(row: dict[str, Any]) -> float | None:
    for key in ("predicted_probability", "model_probability", "probability", "probability_over", "implied_probability"):
        value = _float(row.get(key))
        if value is not None:
            return max(0.0, min(1.0, value / 100 if value > 1 else value))
    return None


def _safe_log(value: float) -> float:
    import math

    return math.log(max(1e-15, min(1 - 1e-15, value)))


def _write_curve(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["bucket", "count", "averageProbability", "observedRate"])
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


def _read_json_or_list(path: Path) -> Any:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, (dict, list)) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _float(value: Any) -> float | None:
    try:
        text = _clean(value)
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def _float_for_model(value: Any) -> float:
    number = _float(value)
    return number if number is not None else 0.0


def _safe_market(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in _clean(value)) or "unknown"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
