from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.market_config import get_market_config
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.services.shadow_model_summary_service import SHADOW_MARKETS, SHADOW_MODEL_KEY, SHADOW_MODEL_STAGE, ShadowModelSummaryService

MANUAL_GOVERNANCE_BLOCKER = "manual_governance_review_required"
MAX_SHADOW_BRIER_SCORE = 0.25
MAX_SHADOW_LOG_LOSS = 0.75


@dataclass(frozen=True)
class ProductionGateResult:
    market: str
    productionGateStatus: str
    productionEligible: bool
    gateChecks: list[dict[str, Any]]
    blockers: list[str]
    warnings: list[str]
    hardBlockers: list[str]
    softWarnings: list[str]
    gateSummary: dict[str, Any]
    freshness: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "productionGateStatus": self.productionGateStatus,
            "productionEligible": self.productionEligible,
            "gateChecks": self.gateChecks,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "hardBlockers": self.hardBlockers,
            "softWarnings": self.softWarnings,
            "gateSummary": self.gateSummary,
            "freshness": self.freshness,
        }


class ModelProductionGateService:
    """Read-only Sprint 19 shadow production gate policy."""

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        summary_service: ShadowModelSummaryService | None = None,
    ) -> None:
        self.settings = settings
        self.summary_service = summary_service or ShadowModelSummaryService(settings)

    def evaluate_market(
        self,
        market: str,
        *,
        shadow: dict[str, Any] | None = None,
        registry: dict[str, Any] | None = None,
    ) -> ProductionGateResult:
        key = normalize_market_key(market)
        if registry is None:
            registry = self.summary_service.registry_service.load_registry()
        shadow = shadow if shadow is not None else self.summary_service.summary_for_market(key, registry=registry)
        registry_shadow = _shadow_registry_entry(registry, key)
        artifact_dir = self.summary_service.artifact_dir(key)
        backtest_path = artifact_dir / "backtest_metrics.json"
        calibration_path = artifact_dir / "calibration.json"
        manifest_path = artifact_dir / "shadow_manifest.json"
        model_path = _resolve_path(_first(registry_shadow, "artifact"), self.settings.root_dir)
        feature_schema_path = _resolve_path(
            _first(registry_shadow, "features", "feature_schema", "featureSchema"),
            self.settings.root_dir,
        )
        metadata_path = _resolve_path(_first(registry_shadow, "metadata", "metadata_path", "metadataPath"), self.settings.root_dir)
        artifact_hash = _text(_first(registry_shadow, "artifact_sha256", "artifactSha256", "sha256"))
        feature_hash = _text(_first(registry_shadow, "features_sha256", "featuresSha256", "feature_schema_sha256", "featureSchemaSha256"))

        checks: list[dict[str, Any]] = []

        def add(
            key_name: str,
            ok: bool | None,
            *,
            severity: str,
            observed: Any,
            expected: Any,
            message: str,
        ) -> None:
            status = "not_applicable" if ok is None else "pass" if ok else "fail"
            checks.append(
                {
                    "key": key_name,
                    "status": status,
                    "severity": severity,
                    "observedValue": observed,
                    "expectedValue": expected,
                    "message": message,
                }
            )

        config = None
        try:
            config = get_market_config(key)
        except KeyError:
            pass

        evaluated_rows = _int(shadow.get("evaluatedRows"))
        positive_rows = _int(shadow.get("positiveRows"))
        negative_rows = _int(shadow.get("negativeRows"))
        brier_score = _float(shadow.get("brierScore"))
        log_loss = _float(shadow.get("logLoss"))
        ece = _float(shadow.get("expectedCalibrationError"))
        validation_dates = list(shadow.get("validationDates") or [])
        split_count = _int(shadow.get("splitCount"))
        fallback_used = bool((shadow.get("provenance") or {}).get("fallbackUsed"))

        add("shadow_artifact_exists", artifact_dir.is_dir(), severity="hard_blocker", observed=_public_path(self.settings.root_dir, artifact_dir), expected="existing Sprint 19 shadow artifact directory", message="Sprint 19 shadow artifact directory must exist.")
        add("model_file_exists", bool(model_path and model_path.is_file()), severity="hard_blocker", observed=_public_path(self.settings.root_dir, model_path) if model_path else "", expected="existing market model file from registry shadow pointer", message="Registry shadow pointer must resolve to an existing model file.")
        add("feature_schema_exists", bool(feature_schema_path and feature_schema_path.is_file()), severity="hard_blocker", observed=_public_path(self.settings.root_dir, feature_schema_path) if feature_schema_path else "", expected="existing feature schema file", message="Feature schema provenance must resolve to an existing file.")
        add("metadata_exists", None if metadata_path is None else metadata_path.is_file(), severity="warning", observed=_public_path(self.settings.root_dir, metadata_path) if metadata_path else "", expected="metadata file when registry declares one", message="Model metadata should be present when expected by registry provenance.")
        add("manifest_exists", manifest_path.is_file(), severity="hard_blocker", observed=_public_path(self.settings.root_dir, manifest_path), expected="shadow_manifest.json", message="Shadow manifest must be present for governance review.")
        add("backtest_exists", backtest_path.is_file(), severity="hard_blocker", observed=_public_path(self.settings.root_dir, backtest_path), expected="backtest_metrics.json", message="Walk-forward backtest artifact must be present.")
        add("calibration_exists", calibration_path.is_file(), severity="hard_blocker", observed=_public_path(self.settings.root_dir, calibration_path), expected="calibration.json", message="Calibration artifact must be present.")
        add("model_stage_is_shadow", shadow.get("modelStage") == SHADOW_MODEL_STAGE, severity="hard_blocker", observed=shadow.get("modelStage"), expected=SHADOW_MODEL_STAGE, message="Only shadow-stage artifacts are evaluated here.")
        add("model_key_is_calibrated_logistic", shadow.get("modelKey") == SHADOW_MODEL_KEY, severity="hard_blocker", observed=shadow.get("modelKey"), expected=SHADOW_MODEL_KEY, message="Sprint 19 shadow gate is scoped to calibrated_logistic.")
        add("registry_shadow_pointer_present", bool(registry_shadow), severity="hard_blocker", observed=bool(registry_shadow), expected=True, message="Registry must contain a shadow calibrated_logistic pointer.")
        add("exact_market_artifact_required", artifact_dir.name == key and artifact_dir.is_dir(), severity="hard_blocker", observed=artifact_dir.name, expected=key, message="Generic or cross-market artifacts are not acceptable for this gate.")
        add("generic_fallback_not_used", not fallback_used, severity="hard_blocker", observed=fallback_used, expected=False, message="Generic fallback must not be used for production gate review.")
        add("evaluated_rows_minimum_met", evaluated_rows is not None and config is not None and evaluated_rows >= config.minimum_training_rows, severity="hard_blocker", observed=evaluated_rows, expected=getattr(config, "minimum_training_rows", "market config"), message="Evaluated rows must meet the market minimum.")
        add("positive_rows_minimum_met", positive_rows is not None and config is not None and positive_rows >= config.minimum_positive_rows, severity="hard_blocker", observed=positive_rows, expected=getattr(config, "minimum_positive_rows", "market config"), message="Positive rows must meet the market minimum.")
        add("negative_rows_minimum_met", negative_rows is not None and negative_rows > 0, severity="hard_blocker", observed=negative_rows, expected="> 0", message="Negative rows must be present.")
        add("validation_dates_present", bool(validation_dates), severity="hard_blocker", observed=validation_dates, expected="one or more validation dates", message="Validation dates must be present.")
        add("split_count_minimum_met", None if split_count is None else split_count >= 1, severity="warning", observed=split_count, expected=">= 1 when splitCount exists", message="Split count should be at least one when reported.")
        add("brier_score_threshold_met", brier_score is not None and brier_score <= MAX_SHADOW_BRIER_SCORE, severity="hard_blocker", observed=brier_score, expected=f"<= {MAX_SHADOW_BRIER_SCORE}", message="Brier score must clear the conservative production threshold.")
        add("log_loss_threshold_met", log_loss is not None and log_loss <= MAX_SHADOW_LOG_LOSS, severity="hard_blocker", observed=log_loss, expected=f"<= {MAX_SHADOW_LOG_LOSS}", message="Log loss must clear the conservative production threshold.")
        add("expected_calibration_error_present", ece is not None, severity="hard_blocker", observed=ece, expected="present", message="Expected calibration error must be reported; missing values are not fabricated.")
        add("expected_calibration_error_threshold_met", None, severity="info", observed=ece, expected="no Sprint 38 ECE threshold configured", message="No ECE threshold policy exists yet, so this check is informational.")
        add("baseline_comparison_available", False, severity="warning", observed="evaluated by readiness baseline block", expected="comparable walk-forward artifact", message="Baseline comparability is reported separately and must not create production eligibility.")
        add("generated_at_present", bool(shadow.get("generatedAt")), severity="warning", observed=shadow.get("generatedAt") or "", expected="generatedAt timestamp", message="Generated timestamp should be present for artifact provenance.")
        add("source_path_present", bool(shadow.get("sourcePath")), severity="warning", observed=shadow.get("sourcePath") or "", expected="sourcePath", message="Source path should be present for artifact provenance.")
        add("artifact_hash_present", bool(artifact_hash), severity="hard_blocker", observed=bool(artifact_hash), expected=True, message="Artifact hash must be present; missing hashes are not fabricated.")
        add("feature_hash_present", bool(feature_hash), severity="hard_blocker", observed=bool(feature_hash), expected=True, message="Feature schema hash must be present; missing hashes are not fabricated.")
        add("fallback_used_false", not fallback_used, severity="hard_blocker", observed=fallback_used, expected=False, message="Fallback artifacts cannot be used for production gate review.")
        add("no_automatic_promotion", False, severity="hard_blocker", observed=False, expected="future explicit manual workflow", message="Automatic promotion is disabled for Sprint 19 shadow models.")
        add("manual_governance_review_required", False, severity="hard_blocker", observed="not completed", expected="future explicit manual governance workflow", message="Manual governance review is required before any separate promotion workflow can be considered.")
        add("research_locks_preserved", shadow.get("readinessLabel") == "Experimental" and shadow.get("action") == "Research" and shadow.get("stakeUnits") == 0 and shadow.get("betActionAllowed") is False, severity="hard_blocker", observed={"readinessLabel": shadow.get("readinessLabel"), "action": shadow.get("action"), "stakeUnits": shadow.get("stakeUnits"), "betActionAllowed": shadow.get("betActionAllowed")}, expected={"readinessLabel": "Experimental", "action": "Research", "stakeUnits": 0, "betActionAllowed": False}, message="Research locks must remain intact.")

        hard_blockers = [check["key"] for check in checks if check["severity"] == "hard_blocker" and check["status"] == "fail"]
        blockers = _dedupe(hard_blockers + _legacy_blocker_aliases(hard_blockers))
        soft_warnings = [check["key"] for check in checks if check["severity"] == "warning" and check["status"] in {"fail", "warn"}]
        status_counts = _status_counts(checks)
        return ProductionGateResult(
            market=key,
            productionGateStatus="manual_review_required" if MANUAL_GOVERNANCE_BLOCKER in hard_blockers else "blocked" if hard_blockers else "pass",
            productionEligible=False,
            gateChecks=checks,
            blockers=blockers,
            warnings=_dedupe(soft_warnings + ["No automatic production promotion is performed by this readiness endpoint."]),
            hardBlockers=blockers,
            softWarnings=_dedupe(soft_warnings),
            gateSummary={
                "status": "manual_review_required" if MANUAL_GOVERNANCE_BLOCKER in hard_blockers else "blocked" if hard_blockers else "pass",
                "productionEligible": False,
                "totalChecks": len(checks),
                "passCount": status_counts.get("pass", 0),
                "failCount": status_counts.get("fail", 0),
                "warningCount": len(soft_warnings),
                "notApplicableCount": status_counts.get("not_applicable", 0),
                "hardBlockerCount": len(hard_blockers),
                "manualGovernanceRequired": True,
            },
            freshness=dict(shadow.get("freshness") or {}),
        )

    def payload(self, *, market: str | None = None, registry: dict[str, Any] | None = None) -> dict[str, Any]:
        requested = [normalize_market_key(market)] if market else list(SHADOW_MARKETS)
        rows = [self.evaluate_market(selected, registry=registry).as_dict() for selected in requested]
        return {
            "schemaVersion": "shadow-production-gates.v1",
            "status": "ok",
            "marketCount": len(rows),
            "readyMarketCount": 0,
            "blockedMarketCount": len(rows),
            "markets": rows,
            "warnings": _dedupe([warning for row in rows for warning in row.get("warnings", [])]),
            "promotionCommandPreview": {
                "enabled": False,
                "informationalOnly": True,
                "message": "Preview only; this endpoint never calls /api/admin/ml-models/promote and does not create a live action.",
                "command": "",
            },
            "policy": {
                "researchOnly": True,
                "automaticPromotionAllowed": False,
                "manualGovernanceReviewRequired": True,
                "productionEligibleForcedFalse": True,
            },
        }


def is_sprint19_shadow_promotion(market: str, source_status: str, model_key: str | None) -> bool:
    return (
        normalize_market_key(market) in SHADOW_MARKETS
        and str(source_status or "").strip().lower() == SHADOW_MODEL_STAGE
        and str(model_key or SHADOW_MODEL_KEY).strip() == SHADOW_MODEL_KEY
    )


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


def _status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in checks:
        status = str(check.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _legacy_blocker_aliases(keys: list[str]) -> list[str]:
    aliases = {
        "shadow_artifact_exists": "missing_shadow_artifact_dir",
        "backtest_exists": "missing_shadow_backtest",
        "calibration_exists": "missing_shadow_calibration",
        "manifest_exists": "missing_shadow_manifest",
        "model_stage_is_shadow": "shadow_status_required",
        "model_key_is_calibrated_logistic": "calibrated_logistic_shadow_required",
        "registry_shadow_pointer_present": "missing_registry_shadow_pointer",
        "model_file_exists": "missing_registry_artifact_file",
        "feature_schema_exists": "missing_feature_schema",
        "artifact_hash_present": "missing_artifact_hash",
        "feature_hash_present": "missing_feature_schema_hash",
        "research_locks_preserved": "research_lock_missing",
        "evaluated_rows_minimum_met": "evaluated_rows_below_market_minimum",
        "positive_rows_minimum_met": "positive_rows_below_market_minimum",
    }
    return [aliases[key] for key in keys if key in aliases]
