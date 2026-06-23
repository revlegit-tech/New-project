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


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out
