from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.market_config import get_market_config
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.shadow_model_summary_service import SHADOW_MARKETS, SHADOW_MODEL_KEY, SHADOW_MODEL_STAGE, ShadowModelSummaryService

READINESS_SCHEMA_VERSION = "shadow-model-readiness.v1"
COMPARABLE_METRICS: tuple[str, ...] = (
    "evaluatedRows",
    "positiveRows",
    "negativeRows",
    "auc",
    "brierScore",
    "logLoss",
    "expectedCalibrationError",
    "sampleCount",
)


class ShadowModelReadinessService:
    """Read-only Sprint 19 shadow-vs-baseline readiness audit."""

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        registry_service: ModelRegistryService | None = None,
        summary_service: ShadowModelSummaryService | None = None,
    ) -> None:
        self.settings = settings
        self.registry_service = registry_service or ModelRegistryService(settings=settings)
        self.summary_service = summary_service or ShadowModelSummaryService(
            settings,
            registry_service=self.registry_service,
        )

    def payload(self, *, market: str | None = None) -> dict[str, Any]:
        requested = [normalize_market_key(market)] if market else list(SHADOW_MARKETS)
        registry = self.registry_service.load_registry()
        markets = [self.readiness_for_market(selected, registry=registry) for selected in requested]
        warnings = _dedupe([warning for row in markets for warning in row.get("warnings", [])])
        return {
            "schemaVersion": READINESS_SCHEMA_VERSION,
            "status": "ok",
            "marketCount": len(markets),
            "readyMarketCount": sum(1 for row in markets if row.get("productionGateStatus") == "pass"),
            "blockedMarketCount": sum(1 for row in markets if row.get("productionGateStatus") != "pass"),
            "markets": markets,
            "warnings": warnings,
            "promotionCommandPreview": {
                "enabled": False,
                "informationalOnly": True,
                "message": "Preview only; this endpoint never calls /api/admin/ml-models/promote and does not create a live action.",
                "command": "",
            },
            "policy": _research_policy(),
        }

    def readiness_for_market(self, market: str, *, registry: dict[str, Any] | None = None) -> dict[str, Any]:
        key = normalize_market_key(market)
        registry = registry if registry is not None else self.registry_service.load_registry()
        shadow = self.summary_service.summary_for_market(key, registry=registry)
        shadow_metrics = _shadow_metrics(shadow)
        baseline = self._baseline_comparison(key, registry=registry)
        gate = self._production_gate(key, shadow=shadow, registry=registry)
        warnings = _dedupe(list(shadow.get("warnings", [])) + list(baseline.get("warnings", [])) + gate["warnings"])
        blockers = _dedupe(gate["blockers"])
        return {
            "market": key,
            "modelStage": SHADOW_MODEL_STAGE,
            "modelKey": SHADOW_MODEL_KEY,
            "version": shadow.get("version") or "",
            "artifactPath": shadow.get("artifactPath") or "",
            "artifactDir": shadow.get("artifactDir") or "",
            "publicPath": shadow.get("artifactDir") or shadow.get("artifactPath") or "",
            "shadow": {
                "source": "sprint19_shadow",
                "modelStage": SHADOW_MODEL_STAGE,
                "modelKey": SHADOW_MODEL_KEY,
                "version": shadow.get("version") or "",
                "artifactPath": shadow.get("artifactPath") or "",
                "artifactDir": shadow.get("artifactDir") or "",
                "backtestPath": shadow.get("backtestPath") or "",
                "calibrationPath": shadow.get("calibrationPath") or "",
                "manifestPath": shadow.get("manifestPath") or "",
                "metrics": shadow_metrics,
                "provenance": shadow.get("provenance") or {},
            },
            "baseline": baseline,
            "metricDeltas": _metric_deltas(shadow_metrics, baseline.get("metrics") or {}),
            "productionGateStatus": "blocked",
            "productionEligible": False,
            "blockers": blockers,
            "warnings": warnings,
            "recommendedNextStep": _recommended_next_step(blockers, baseline),
            "promotionCommandPreview": {
                "enabled": False,
                "informationalOnly": True,
                "message": "Review-only preview; no promotion endpoint is called.",
                "command": "",
            },
            **_research_policy(),
        }

    def _baseline_comparison(self, market: str, *, registry: dict[str, Any]) -> dict[str, Any]:
        baseline_dir = self.settings.data_dir / "models" / "baseline" / market
        baseline_backtest = _read_json(baseline_dir / "backtest_metrics.json")
        baseline_calibration = _read_json(baseline_dir / "calibration.json")
        baseline_metrics = _merge_metrics(baseline_backtest, baseline_calibration)
        warnings: list[str] = []
        source = "missing"
        artifact_path = ""
        public_path = ""

        if baseline_metrics:
            source = "baseline_fallback"
            public_path = _public_path(self.settings.root_dir, baseline_dir)
        legacy = _legacy_registry_entry(registry, market)
        if legacy:
            source = str(legacy.get("source") or "legacy")
            artifact_path = _public_path(self.settings.root_dir, _resolve_path(legacy.get("artifact"), self.settings.root_dir))
            legacy_metrics = _merge_metrics(_dict(legacy.get("backtest")), _dict(legacy.get("metrics")))
            if legacy_metrics:
                baseline_metrics = {**baseline_metrics, **legacy_metrics}
            public_path = artifact_path or public_path

        if not baseline_metrics:
            warnings.append("No comparable baseline or legacy metrics were found; shadow readiness still returns safely.")
        return {
            "source": source,
            "artifactPath": artifact_path,
            "publicPath": public_path,
            "metrics": baseline_metrics,
            "provenance": {
                "baselineBacktestPath": _public_path(self.settings.root_dir, baseline_dir / "backtest_metrics.json"),
                "baselineCalibrationPath": _public_path(self.settings.root_dir, baseline_dir / "calibration.json"),
                "legacyRegistryStage": str(legacy.get("stage") or "") if legacy else "",
                "legacyModelKey": str(legacy.get("modelKey") or legacy.get("model_key") or "") if legacy else "",
            },
            "warnings": warnings,
        }

    def _production_gate(self, market: str, *, shadow: dict[str, Any], registry: dict[str, Any]) -> dict[str, list[str]]:
        blockers: list[str] = []
        warnings: list[str] = []
        artifact_dir = self.summary_service.artifact_dir(market)
        registry_shadow = _shadow_registry_entry(registry, market)
        config = None
        try:
            config = get_market_config(market)
        except KeyError:
            blockers.append("missing_market_config")

        if not artifact_dir.is_dir():
            blockers.append("missing_shadow_artifact_dir")
        if not (artifact_dir / "backtest_metrics.json").is_file():
            blockers.append("missing_shadow_backtest")
        if not (artifact_dir / "calibration.json").is_file():
            blockers.append("missing_shadow_calibration")
        if shadow.get("modelStage") != SHADOW_MODEL_STAGE:
            blockers.append("shadow_status_required")
        if shadow.get("modelKey") != SHADOW_MODEL_KEY:
            blockers.append("calibrated_logistic_shadow_required")

        evaluated_rows = _int(shadow.get("evaluatedRows"))
        positive_rows = _int(shadow.get("positiveRows"))
        if config is not None:
            if evaluated_rows is None or evaluated_rows < config.minimum_training_rows:
                blockers.append("evaluated_rows_below_market_minimum")
            if positive_rows is None or positive_rows < config.minimum_positive_rows:
                blockers.append("positive_rows_below_market_minimum")

        if shadow.get("backtestStatus") != "ready":
            blockers.append("shadow_backtest_not_ready")
        if shadow.get("calibrationStatus") != "ready":
            blockers.append("shadow_calibration_not_ready")
        if shadow.get("readinessLabel") != "Experimental" or shadow.get("action") != "Research":
            blockers.append("research_lock_missing")
        if shadow.get("stakeUnits") != 0 or shadow.get("betActionAllowed") is not False:
            blockers.append("research_bet_action_lock_missing")

        artifact_hash = _text(_first(registry_shadow, "artifact_sha256", "artifactSha256", "sha256"))
        features_hash = _text(_first(registry_shadow, "features_sha256", "featuresSha256", "feature_schema_sha256", "featureSchemaSha256"))
        artifact_path = _resolve_path(_first(registry_shadow, "artifact"), self.settings.root_dir)
        features_path = _resolve_path(_first(registry_shadow, "features", "feature_schema", "featureSchema"), self.settings.root_dir)
        if not registry_shadow:
            blockers.append("missing_registry_shadow_pointer")
        if not artifact_hash:
            blockers.append("missing_artifact_hash")
        if not features_hash:
            blockers.append("missing_feature_schema_hash")
        if not artifact_path or not artifact_path.is_file():
            blockers.append("missing_registry_artifact_file")
        if not features_path or not features_path.is_file():
            blockers.append("missing_feature_schema")

        blockers.append("manual_governance_review_required")
        warnings.append("No automatic production promotion is performed by this readiness endpoint.")
        return {"blockers": _dedupe(blockers), "warnings": warnings}


def _research_policy() -> dict[str, Any]:
    return {
        "readinessLabel": "Experimental",
        "action": "Research",
        "stakeUnits": 0,
        "betActionAllowed": False,
    }


def _shadow_metrics(shadow: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluatedRows": shadow.get("evaluatedRows"),
        "positiveRows": shadow.get("positiveRows"),
        "negativeRows": shadow.get("negativeRows"),
        "auc": shadow.get("auc"),
        "brierScore": shadow.get("brierScore"),
        "logLoss": shadow.get("logLoss"),
        "expectedCalibrationError": shadow.get("expectedCalibrationError"),
        "sampleCount": shadow.get("sampleCount") or shadow.get("evaluatedRows"),
        "validationDates": list(shadow.get("validationDates") or []),
        "generatedAt": shadow.get("generatedAt") or "",
    }


def _merge_metrics(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        for key in COMPARABLE_METRICS:
            value = payload.get(key)
            if value not in {None, ""}:
                merged[key] = value
        if payload.get("validationDates"):
            merged["validationDates"] = list(payload.get("validationDates") or [])
        if payload.get("generatedAt"):
            merged["generatedAt"] = payload.get("generatedAt")
    return merged


def _metric_deltas(shadow: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    deltas: dict[str, Any] = {}
    for key in COMPARABLE_METRICS:
        left = _float(shadow.get(key))
        right = _float(baseline.get(key))
        if left is None or right is None:
            continue
        deltas[key] = round(left - right, 12)
    return deltas


def _recommended_next_step(blockers: list[str], baseline: dict[str, Any]) -> str:
    if "missing_shadow_backtest" in blockers or "missing_shadow_calibration" in blockers:
        return "Generate missing Sprint 19 shadow backtest/calibration artifacts, then rerun readiness."
    if any("hash" in blocker or "feature_schema" in blocker or "registry" in blocker for blocker in blockers):
        return "Repair registry artifact, feature schema, and hash provenance before any manual promotion review."
    if baseline.get("source") == "missing":
        return "Add a comparable baseline or legacy evaluation artifact for side-by-side review."
    if blockers:
        return "Resolve listed production gate blockers and rerun the read-only audit."
    return "All checked gates passed; perform manual governance review before considering a separate promotion workflow."


def _legacy_registry_entry(registry: dict[str, Any], market: str) -> dict[str, Any]:
    raw_market = registry.get(normalize_market_key(market))
    if not isinstance(raw_market, dict):
        return {}
    for stage in ("production", "experimental", "candidate"):
        stage_entry = raw_market.get(stage)
        if not isinstance(stage_entry, dict):
            continue
        if stage == SHADOW_MODEL_STAGE:
            continue
        entry = dict(stage_entry)
        entry["stage"] = stage
        entry["source"] = f"legacy_{stage}"
        return entry
    if any(key in raw_market for key in ("artifact", "artifact_sha256", "artifactSha256", "status", "version")):
        entry = dict(raw_market)
        entry["stage"] = "production"
        entry["source"] = "legacy_production"
        return entry
    return {}


def _shadow_registry_entry(registry: dict[str, Any], market: str) -> dict[str, Any]:
    raw_market = registry.get(normalize_market_key(market))
    if not isinstance(raw_market, dict):
        return {}
    shadow = raw_market.get(SHADOW_MODEL_STAGE)
    if not isinstance(shadow, dict):
        return {}
    models = shadow.get("models")
    if isinstance(models, dict) and isinstance(models.get(SHADOW_MODEL_KEY), dict):
        merged = dict(shadow)
        merged.update(models[SHADOW_MODEL_KEY])
        return merged
    selected = _text(_first(shadow, "selected_model", "selectedModel", "model_key", "modelKey"))
    if selected and selected != SHADOW_MODEL_KEY:
        return {}
    return dict(shadow)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_path(value: Any, root: Path) -> Path | None:
    text = _text(value)
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else (root / path)


def _public_path(root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _first(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in {None, ""}:
            return mapping[key]
    return default


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
