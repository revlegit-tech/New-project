from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.player_prop_model_runtime import first_value, model_market_key, to_float
from mlb_app.services.prop_side_normalization import normalize_prop_side

SCHEMA_VERSION = "player-prop-calibration.v1"
DEFAULT_MIN_SAMPLE = 200
MAX_BRIER_DEGRADATION = 0.0025


@dataclass(frozen=True)
class CalibrationResult:
    raw_probability: float
    calibrated_probability: float | None
    applied_probability: float
    applied: bool
    status: str
    method: str
    artifact_path: str
    artifact_generated_at: str
    warnings: list[str]


class PlayerPropModelCalibrationService:
    """Train and apply evaluation-only player prop probability calibrators."""

    def __init__(self, *, settings: Settings = default_settings, min_sample: int = DEFAULT_MIN_SAMPLE) -> None:
        self.settings = settings
        self.min_sample = int(min_sample)

    def artifact_path(self, market: str) -> Path:
        key = model_market_key(market) or "unknown"
        return self.settings.model_dir / "calibration" / f"player_prop_calibration_{key}.joblib"

    def apply(self, *, market: str, probability: float) -> CalibrationResult:
        raw = _clamp_probability(probability)
        path = self.artifact_path(market)
        if not path.is_file():
            return CalibrationResult(raw, None, raw, False, "not_available", "", "", "", ["calibration artifact missing"])

        try:
            from joblib import load

            artifact = load(path)
        except Exception as exc:
            return CalibrationResult(raw, None, raw, False, "failed_quality_gate", "", str(path), "", [f"calibration artifact load failed: {exc}"])

        gates = self._quality_warnings(artifact, market=market)
        method = str(artifact.get("method") or "")
        generated_at = str(artifact.get("generatedAt") or "")
        if _sample_size(artifact) < int(artifact.get("minSampleSize") or self.min_sample):
            return CalibrationResult(raw, None, raw, False, "insufficient_sample", method, str(path), generated_at, gates)
        if gates:
            return CalibrationResult(raw, None, raw, False, "failed_quality_gate", method, str(path), generated_at, gates)

        try:
            calibrated = _predict_calibrated_probability(artifact, raw)
        except Exception as exc:
            return CalibrationResult(raw, None, raw, False, "failed_quality_gate", method, str(path), generated_at, [f"calibration prediction failed: {exc}"])
        if calibrated is None or math.isnan(calibrated) or calibrated < 0.0 or calibrated > 1.0:
            return CalibrationResult(raw, None, raw, False, "failed_quality_gate", method, str(path), generated_at, ["calibrated probability outside [0, 1]"])

        return CalibrationResult(raw, calibrated, calibrated, True, "applied", method, str(path), generated_at, [])

    def calibrate(
        self,
        *,
        input_path: Path | str | None = None,
        market: str = "",
        method: str = "isotonic",
        output_path: Path | str | None = None,
        min_sample: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        selected_market = model_market_key(market)
        if not selected_market:
            raise ValueError("market is required")
        selected_method = method.strip().lower() or "isotonic"
        selected_min_sample = int(min_sample or self.min_sample)
        source_path = Path(input_path) if input_path else self.settings.data_dir / "training" / "historical_props_from_ml_labels_joined.csv"
        out_path = Path(output_path) if output_path else self.artifact_path(selected_market)
        rows = calibration_rows(_read_csv_rows(source_path), market=selected_market)
        warnings: list[str] = []
        if len(rows) < selected_min_sample:
            warnings.append(f"Calibration sample size is low: {len(rows)} < {selected_min_sample}.")

        metrics: dict[str, Any] = {}
        artifact_written = False
        if rows:
            artifact = _fit_artifact(rows, market=selected_market, method=selected_method, min_sample=selected_min_sample)
            metrics = {key: value for key, value in artifact.items() if key != "calibrator"}
            warnings.extend(str(item) for item in artifact.get("warnings") or [])
            if not dry_run:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                from joblib import dump

                dump(artifact, out_path)
                artifact_written = True
        elif not source_path.is_file():
            warnings.append(f"Calibration input file not found: {source_path}")
        else:
            warnings.append(f"No calibration rows found for market {selected_market}.")

        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok",
            "market": selected_market,
            "method": selected_method,
            "inputPath": str(source_path),
            "artifactPath": str(out_path),
            "artifactWritten": artifact_written,
            "dryRun": bool(dry_run),
            "sampleSize": len(rows),
            "minSampleSize": selected_min_sample,
            "metrics": metrics,
            "warnings": _dedupe(warnings),
        }

    def _quality_warnings(self, artifact: dict[str, Any], *, market: str) -> list[str]:
        warnings: list[str] = []
        artifact_market = model_market_key(artifact.get("market"))
        if artifact_market != model_market_key(market):
            warnings.append("calibration artifact market mismatch")
        sample_size = _sample_size(artifact)
        if sample_size < int(artifact.get("minSampleSize") or self.min_sample):
            warnings.append(f"calibration sample size below minimum: {sample_size}")
        before = _float_or_none(artifact.get("brierScoreBefore"))
        after = _float_or_none(artifact.get("brierScoreAfter"))
        if before is None or after is None:
            warnings.append("calibration brier metadata missing")
        elif after > before + MAX_BRIER_DEGRADATION:
            warnings.append("calibration failed brier quality gate")
        if artifact.get("status") and artifact.get("status") != "ready":
            warnings.append(f"calibration artifact status is {artifact.get('status')}")
        return _dedupe(warnings)


def calibration_rows(rows: Iterable[dict[str, Any]], *, market: str) -> list[dict[str, float]]:
    selected_market = model_market_key(market)
    out: list[dict[str, float]] = []
    for row in rows:
        if model_market_key(first_value(row, ["market", "baseMarket"], "")) != selected_market:
            continue
        probability = _probability(row)
        target_over = _target_over(row)
        if probability is None or target_over is None:
            continue
        side = normalize_prop_side(
            first_value(row, ["side"], ""),
            first_value(row, ["rawLabel", "raw_label"], ""),
            first_value(row, ["label", "title", "name"], ""),
            first_value(row, ["outcome", "outcomeName", "outcome_name", "selection"], ""),
        )
        target = float(target_over)
        if str(side).lower().startswith("under"):
            probability = 1.0 - probability
            target = 1.0 - target
        out.append({"probability": _clamp_probability(probability), "target": target, "date": _date_ordinal(row)})
    return out


def _fit_artifact(rows: list[dict[str, float]], *, market: str, method: str, min_sample: int) -> dict[str, Any]:
    probabilities = [row["probability"] for row in rows]
    targets = [row["target"] for row in rows]
    warnings: list[str] = []
    calibrator: Any
    selected_method = method
    if method in {"platt", "logistic", "logistic_regression"}:
        from sklearn.linear_model import LogisticRegression

        calibrator = LogisticRegression(solver="lbfgs")
        calibrator.fit([[p] for p in probabilities], targets)
        selected_method = "platt"
        calibrated = [float(calibrator.predict_proba([[p]])[0][1]) for p in probabilities]
    elif method == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrator.fit(probabilities, targets)
        calibrated = [float(calibrator.predict([p])[0]) for p in probabilities]
    else:
        raise ValueError("Unsupported calibration method. Use isotonic or platt.")

    brier_before = _brier(probabilities, targets)
    brier_after = _brier(calibrated, targets)
    log_loss_before = _log_loss(probabilities, targets)
    log_loss_after = _log_loss(calibrated, targets)
    if brier_after > brier_before + MAX_BRIER_DEGRADATION:
        warnings.append("Calibration made Brier score materially worse.")
    if any(value < 0.0 or value > 1.0 or math.isnan(value) for value in calibrated):
        warnings.append("Calibrated probabilities were outside [0, 1].")
    date_values = [row["date"] for row in rows if row.get("date")]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "version": SCHEMA_VERSION,
        "status": "ready" if len(rows) >= min_sample and not warnings else "needs_review",
        "market": market,
        "method": selected_method,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "trainingDateRange": _date_range(date_values),
        "sampleSize": len(rows),
        "minSampleSize": min_sample,
        "brierScoreBefore": brier_before,
        "brierScoreAfter": brier_after,
        "logLossBefore": log_loss_before,
        "logLossAfter": log_loss_after,
        "warnings": warnings,
        "calibrator": calibrator,
    }


def _predict_calibrated_probability(artifact: dict[str, Any], probability: float) -> float:
    calibrator = artifact.get("calibrator")
    method = str(artifact.get("method") or "").lower()
    if hasattr(calibrator, "predict_proba"):
        return float(calibrator.predict_proba([[probability]])[0][1])
    if hasattr(calibrator, "predict"):
        return float(calibrator.predict([probability])[0])
    mapping = artifact.get("mapping")
    if isinstance(mapping, dict):
        slope = _float_or_none(mapping.get("slope")) or 1.0
        intercept = _float_or_none(mapping.get("intercept")) or 0.0
        return _clamp_probability(probability * slope + intercept)
    raise ValueError(f"Unsupported calibration artifact method: {method or 'unknown'}")


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _probability(row: dict[str, Any]) -> float | None:
    value = first_value(row, ["rawModelProbability", "model_probability", "model_probability_percent", "modelProbabilityPercent", "finalProbabilityPercent", "probability"], "")
    parsed = to_float(value, math.nan)
    if math.isnan(parsed):
        return None
    return _clamp_probability(parsed / 100.0 if parsed > 1.0 else parsed)


def _target_over(row: dict[str, Any]) -> int | None:
    over = str(first_value(row, ["over", "target_over"], "")).strip().lower()
    if over in {"1", "true", "yes", "y"}:
        return 1
    if over in {"0", "false", "no", "n"}:
        return 0
    result = str(first_value(row, ["result", "target_result", "hit"], "")).strip().lower()
    if result in {"hit", "win", "won", "over", "1", "true", "yes"}:
        return 1
    if result in {"miss", "loss", "lost", "under", "0", "false", "no"}:
        return 0
    actual = _float_or_none(first_value(row, ["actual", "actual_value", "actualStat"], ""))
    line = _float_or_none(first_value(row, ["line"], ""))
    if actual is not None and line is not None and actual != line:
        return 1 if actual > line else 0
    return None


def _date_ordinal(row: dict[str, Any]) -> float:
    text = str(first_value(row, ["date", "game_date", "gameDate"], "")).strip()
    try:
        return float(datetime.fromisoformat(text).date().toordinal())
    except ValueError:
        return 0.0


def _date_range(ordinals: list[float]) -> dict[str, str]:
    if not ordinals:
        return {"start": "", "end": ""}
    start = datetime.fromordinal(int(min(ordinals))).date().isoformat()
    end = datetime.fromordinal(int(max(ordinals))).date().isoformat()
    return {"start": start, "end": end}


def _sample_size(artifact: dict[str, Any]) -> int:
    return int(artifact.get("sampleSize") or artifact.get("sample_count") or artifact.get("sampleCount") or 0)


def _brier(probabilities: list[float], targets: list[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probabilities, targets, strict=False)) / max(len(targets), 1)


def _log_loss(probabilities: list[float], targets: list[float]) -> float:
    return -sum(y * math.log(_clip_log(p)) + (1 - y) * math.log(_clip_log(1 - p)) for p, y in zip(probabilities, targets, strict=False)) / max(len(targets), 1)


def _clip_log(value: float) -> float:
    return max(1e-15, min(1 - 1e-15, value))


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _float_or_none(value: Any) -> float | None:
    parsed = to_float(value, math.nan)
    return None if math.isnan(parsed) else float(parsed)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
