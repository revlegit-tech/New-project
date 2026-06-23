from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlb_app.ml.datasets.leakage_guard import assert_feature_columns_safe
from mlb_app.ml.market_config import MarketModelConfig

MODEL_REGISTRY_STATUSES: tuple[str, ...] = (
    "disabled",
    "candidate",
    "shadow",
    "production",
    "deprecated",
)

PRODUCTION_TARGET_STATUS = "production"

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "disabled": frozenset({"candidate", "deprecated"}),
    "candidate": frozenset({"shadow", "disabled", "deprecated"}),
    "shadow": frozenset({"production", "disabled", "deprecated"}),
    "production": frozenset({"disabled", "deprecated"}),
    "deprecated": frozenset(),
}


@dataclass(frozen=True)
class PromotionValidationResult:
    allowed: bool
    target_status: str
    reasons: tuple[str, ...] = ()
    market: str = ""
    source_status: str = ""
    checks: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "allowed": self.allowed,
            "target_status": self.target_status,
            "reasons": list(self.reasons),
        }
        if self.market:
            payload["market"] = self.market
        if self.source_status:
            payload["source_status"] = self.source_status
        if self.checks:
            payload["checks"] = dict(self.checks)
        return payload


def validate_promotion_gate(
    *,
    market: str,
    entry: dict[str, Any],
    target_status: str,
    source_status: str,
    market_config: MarketModelConfig | None,
    artifact_path: Path | None,
    feature_schema_path: Path | None,
    allow_candidate_to_production: bool = False,
    allow_deprecated_to_production: bool = False,
) -> PromotionValidationResult:
    target = _normalize_status(target_status)
    source = _normalize_status(source_status or entry.get("status"))
    reasons: list[str] = []
    checks: dict[str, Any] = {
        "artifactExists": bool(artifact_path and artifact_path.exists()),
        "featureSchemaExists": bool(feature_schema_path and feature_schema_path.exists()),
        "trainingRows": _int(entry.get("training_rows") or entry.get("trainingRows")),
        "positiveRows": _int(entry.get("positive_rows") or entry.get("positiveRows")),
        "calibrated": bool(entry.get("calibrated")),
    }

    if source not in MODEL_REGISTRY_STATUSES:
        reasons.append("unsupported_source_status")
    if target not in MODEL_REGISTRY_STATUSES:
        reasons.append("unsupported_target_status")

    direct_candidate_override = target == PRODUCTION_TARGET_STATUS and source == "candidate" and allow_candidate_to_production
    direct_deprecated_override = target == PRODUCTION_TARGET_STATUS and source == "deprecated" and allow_deprecated_to_production
    if source in MODEL_REGISTRY_STATUSES and target in MODEL_REGISTRY_STATUSES:
        if target not in _ALLOWED_TRANSITIONS.get(source, frozenset()):
            if not direct_candidate_override and not direct_deprecated_override:
                reasons.append(f"{source}_to_{target}_blocked")

    if target == PRODUCTION_TARGET_STATUS:
        _validate_production_requirements(
            reasons=reasons,
            checks=checks,
            market=market,
            entry=entry,
            source_status=source,
            market_config=market_config,
            artifact_path=artifact_path,
            feature_schema_path=feature_schema_path,
            allow_candidate_to_production=allow_candidate_to_production,
            allow_deprecated_to_production=allow_deprecated_to_production,
        )

    return PromotionValidationResult(
        allowed=not reasons,
        target_status=target,
        reasons=tuple(_dedupe(reasons)),
        market=str(market),
        source_status=source,
        checks=checks,
    )


def _validate_production_requirements(
    *,
    reasons: list[str],
    checks: dict[str, Any],
    market: str,
    entry: dict[str, Any],
    source_status: str,
    market_config: MarketModelConfig | None,
    artifact_path: Path | None,
    feature_schema_path: Path | None,
    allow_candidate_to_production: bool,
    allow_deprecated_to_production: bool,
) -> None:
    if source_status == "candidate" and not allow_candidate_to_production:
        reasons.append("candidate_to_production_blocked")
    if source_status == "deprecated" and not allow_deprecated_to_production:
        reasons.append("deprecated_to_production_blocked")
    direct_override = (
        source_status == "candidate" and allow_candidate_to_production
    ) or (
        source_status == "deprecated" and allow_deprecated_to_production
    )
    if source_status != "shadow" and not direct_override:
        reasons.append("shadow_status_required")

    if market_config is None:
        reasons.append("missing_market_config")
    else:
        checks["minimumTrainingRows"] = market_config.minimum_training_rows
        checks["minimumPositiveRows"] = market_config.minimum_positive_rows
        checks["marketConfigModelAllowed"] = _model_allowed(entry, market_config)
        checks["calibrationRequired"] = _requires_calibration(market_config)
        if not checks["marketConfigModelAllowed"]:
            reasons.append("model_not_allowed_for_market")
        if checks["trainingRows"] < market_config.minimum_training_rows:
            reasons.append("low_training_rows")
        if checks["positiveRows"] < market_config.minimum_positive_rows:
            reasons.append("low_positive_rows")
        if checks["calibrationRequired"] and not checks["calibrated"]:
            reasons.append("calibration_required")

    if not artifact_path or not artifact_path.exists():
        reasons.append("missing_artifact")
    if not feature_schema_path or not feature_schema_path.exists():
        reasons.append("missing_feature_schema")
    elif not _feature_schema_is_valid(feature_schema_path):
        reasons.append("invalid_feature_schema")

    entry_market = str(entry.get("market") or market or "").strip()
    if entry_market and str(market).strip() and entry_market != str(market).strip():
        reasons.append("market_mismatch")

    if _is_actionnetwork_source(entry):
        _validate_actionnetwork_production_requirements(reasons=reasons, checks=checks, entry=entry)


def _validate_actionnetwork_production_requirements(
    *,
    reasons: list[str],
    checks: dict[str, Any],
    entry: dict[str, Any],
) -> None:
    clean_days = _int(_first(entry, "clean_forward_days", "cleanForwardDays", "forward_collection_days", "forwardCollectionDays"))
    min_clean_days = _int(_first(entry, "minimum_clean_forward_days", "minimumCleanForwardDays", "min_clean_forward_days", "minCleanForwardDays"), 14)
    event_labels = _int(_first(entry, "event_confirmed_labels", "eventConfirmedLabels", "event_confirmed_label_count", "eventConfirmedLabelCount"))
    min_event_labels = _int(_first(entry, "minimum_event_confirmed_labels", "minimumEventConfirmedLabels", "min_event_confirmed_labels", "minEventConfirmedLabels"), 100)
    diagnostic_rows = _int(_first(entry, "diagnostic_rows", "diagnosticRows", "diagnostic_past_rows", "diagnosticPastRows"))
    date_only_rows = _int(_first(entry, "date_only_rows", "dateOnlyRows", "date_only_label_rows", "dateOnlyLabelRows"))
    reused_rows = _int(_first(entry, "reused_board_rows", "reusedBoardRows", "reused_board_suspect_rows", "reusedBoardSuspectRows"))
    push_rows = _int(_first(entry, "push_rows", "pushRows"))
    walk_forward_rows = _int(_first(entry, "walk_forward_rows", "walkForwardRows", "walk_forward_sample_count", "walkForwardSampleCount"))
    min_walk_forward_rows = _int(_first(entry, "minimum_walk_forward_rows", "minimumWalkForwardRows", "min_walk_forward_rows", "minWalkForwardRows"), 100)
    shadow_roi = _float(_first(entry, "shadow_roi", "shadowRoi", "shadow_roi_percent", "shadowRoiPercent"))
    min_shadow_roi = _float(_first(entry, "minimum_shadow_roi", "minimumShadowRoi", "min_shadow_roi", "minShadowRoi", "min_shadow_roi_percent", "minShadowRoiPercent"), 0.0)
    shadow_clv = _float(_first(entry, "shadow_clv", "shadowClv", "average_clv", "averageClv"))
    min_shadow_clv = _float(_first(entry, "minimum_shadow_clv", "minimumShadowClv", "min_shadow_clv", "minShadowClv"), None)
    calibration_passed = _bool(_first(entry, "calibration_metrics_passed", "calibrationMetricsPassed", "calibration_passed", "calibrationPassed"), default=True)
    forward_only = _bool(_first(entry, "actionnetwork_forward_only", "actionnetworkForwardOnly", "forward_only", "forwardOnly"), default=True)

    checks["actionnetwork"] = {
        "forwardOnly": forward_only,
        "cleanForwardDays": clean_days,
        "minimumCleanForwardDays": min_clean_days,
        "eventConfirmedLabels": event_labels,
        "minimumEventConfirmedLabels": min_event_labels,
        "diagnosticRows": diagnostic_rows,
        "dateOnlyRows": date_only_rows,
        "reusedBoardRows": reused_rows,
        "pushRows": push_rows,
        "calibrationMetricsPassed": calibration_passed,
        "walkForwardRows": walk_forward_rows,
        "minimumWalkForwardRows": min_walk_forward_rows,
        "shadowRoi": shadow_roi,
        "minimumShadowRoi": min_shadow_roi,
        "shadowClv": shadow_clv,
        "minimumShadowClv": min_shadow_clv,
    }

    collection_modes = _strings(_first(entry, "collection_modes", "collectionModes"))
    if not forward_only or any(mode != "live_forward" for mode in collection_modes):
        reasons.append("actionnetwork_forward_only")
    if clean_days < min_clean_days:
        reasons.append("min_clean_forward_days")
    if event_labels < min_event_labels:
        reasons.append("min_event_confirmed_labels")
    if diagnostic_rows > 0:
        reasons.append("no_diagnostic_rows")
    if date_only_rows > 0:
        reasons.append("no_date_only_rows")
    if reused_rows > 0:
        reasons.append("no_reused_board_rows")
    if push_rows > 0:
        reasons.append("no_push_rows")
    if not calibration_passed:
        reasons.append("calibration_metrics_failed")
    if walk_forward_rows < min_walk_forward_rows:
        reasons.append("walk_forward_sample_threshold")
    if shadow_roi is None or (min_shadow_roi is not None and shadow_roi < min_shadow_roi):
        reasons.append("shadow_roi_threshold")
    if min_shadow_clv is not None and (shadow_clv is None or shadow_clv < min_shadow_clv):
        reasons.append("shadow_clv_threshold")


def _model_allowed(entry: dict[str, Any], market_config: MarketModelConfig) -> bool:
    model_key = str(entry.get("model_key") or entry.get("modelKey") or entry.get("model_type") or "").strip()
    return bool(model_key and model_key in set(market_config.candidate_models))


def _requires_calibration(market_config: MarketModelConfig) -> bool:
    return bool(str(market_config.recommended_calibration or "").strip())


def _feature_schema_is_valid(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            feature_names = tuple(str(item).strip() for item in payload if str(item).strip())
        elif isinstance(payload, dict):
            raw = payload.get("feature_names") or payload.get("featureNames") or payload.get("features") or payload.get("columns")
            if isinstance(raw, str):
                feature_names = (raw.strip(),) if raw.strip() else ()
            elif isinstance(raw, (list, tuple)):
                feature_names = tuple(str(item).strip() for item in raw if str(item).strip())
            else:
                feature_names = ()
        else:
            return False
        if not feature_names:
            return False
        assert_feature_columns_safe(feature_names)
        return True
    except Exception:
        return False


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_actionnetwork_source(entry: dict[str, Any]) -> bool:
    source = " ".join(
        _strings(
            [
                entry.get("source"),
                entry.get("sourceSystem"),
                entry.get("source_system"),
                entry.get("dataSource"),
                entry.get("data_source"),
                entry.get("provider"),
            ]
        )
    ).lower()
    return "actionnetwork" in source or bool(entry.get("actionnetwork") or entry.get("actionNetwork"))


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, *, default: bool) -> bool:
    if value in {None, ""}:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _first(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key not in mapping:
            continue
        value = mapping[key]
        if value is None or value == "":
            continue
        return value
    return default


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out
