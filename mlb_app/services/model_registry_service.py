from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.market_config import get_market_config, is_supported_market
from mlb_app.ml.registry.metadata import utc_now_iso
from mlb_app.ml.registry.promotion_gates import PromotionValidationResult, validate_promotion_gate
from mlb_app.repositories.csv_store import CsvStore
from mlb_app.repositories.model_artifact_repository import ModelArtifactRepository
from mlb_app.repositories.model_store import ModelStore, normalize_market_key

DEFAULT_MARKETS: tuple[str, ...] = (
    "pitcher_strikeouts",
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
    "team_first_score",
)

MIN_TRAINING_ROWS = 25
MIN_PRODUCTION_BACKTEST_ROWS = 100
MAX_PRODUCTION_BRIER_SCORE = 0.25
MAX_PRODUCTION_LOG_LOSS = 0.75
PRODUCTION_STATUSES = {"production_candidate", "production"}
DISABLED_STATUSES = {"disabled", "blocked"}
SPRINT19_ALLOWED_MODEL_STATUSES = {"disabled", "candidate", "shadow", "deprecated"}
TRAINING_RUNNER_STATUSES = {"candidate", "shadow"}


@dataclass(frozen=True)
class MarketTrainingStats:
    total_rows: int
    positive_rows: int
    negative_rows: int
    class_counts: dict[str, int]
    source: str = "csv"

    @property
    def has_two_classes(self) -> bool:
        return self.positive_rows > 0 and self.negative_rows > 0

    @property
    def can_train(self) -> bool:
        return self.total_rows >= MIN_TRAINING_ROWS and self.has_two_classes


@dataclass(frozen=True)
class BacktestGate:
    graded: int
    brier_score: float | None = None
    log_loss: float | None = None
    roi_percent: float | None = None
    source: str = "registry"

    @property
    def has_enough_rows(self) -> bool:
        return self.graded >= MIN_PRODUCTION_BACKTEST_ROWS

    @property
    def brier_ok(self) -> bool:
        return self.brier_score is None or self.brier_score <= MAX_PRODUCTION_BRIER_SCORE

    @property
    def log_loss_ok(self) -> bool:
        return self.log_loss is None or self.log_loss <= MAX_PRODUCTION_LOG_LOSS

    @property
    def ok_for_production(self) -> bool:
        return self.has_enough_rows and self.brier_ok and self.log_loss_ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "graded": self.graded,
            "brierScore": self.brier_score,
            "logLoss": self.log_loss,
            "roiPercent": self.roi_percent,
            "source": self.source,
            "hasEnoughRows": self.has_enough_rows,
            "brierOk": self.brier_ok,
            "logLossOk": self.log_loss_ok,
            "okForProduction": self.ok_for_production,
            "minimumRows": MIN_PRODUCTION_BACKTEST_ROWS,
            "maxBrierScore": MAX_PRODUCTION_BRIER_SCORE,
            "maxLogLoss": MAX_PRODUCTION_LOG_LOSS,
        }


class ModelRegistryService:
    """Single source of truth for production-facing market readiness.

    Phase 13 makes model readiness auditable. A market can only become
    production-eligible when all of these are true:

    * an exact market-specific artifact exists
    * feature metadata exists
    * the market has enough two-class training data
    * the artifact is marked calibrated
    * the registry status is production_candidate or production
    * backtest metrics clear the minimum production gates

    Generic prop-model fallback remains prohibited for the trust surface.
    """

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        csv_store: CsvStore | None = None,
        model_store: ModelStore | None = None,
        artifact_repository: ModelArtifactRepository | None = None,
    ) -> None:
        self.settings = settings
        self.csv_store = csv_store or CsvStore()
        self.model_store = model_store or ModelStore(settings.model_dir)
        self.artifact_repository = artifact_repository or ModelArtifactRepository(settings)

    def training_stats(self, market: str, *, registry_entry: dict[str, Any] | None = None) -> MarketTrainingStats:
        key = normalize_market_key(market)
        path = self.settings.data_dir / "training" / f"{key}_training.csv"
        rows = _read_csv_rows_cached(self.csv_store, path)
        if rows:
            counts: Counter[str] = Counter()
            for row in rows:
                value = str(row.get("over", row.get("target", row.get("label", "")))).strip()
                if value in {"0", "1"}:
                    counts[value] += 1
            return MarketTrainingStats(
                total_rows=len(rows),
                positive_rows=counts.get("1", 0),
                negative_rows=counts.get("0", 0),
                class_counts=dict(counts),
                source="csv",
            )

        # Registry counts are allowed for audit display when raw training files
        # are not shipped with the runtime. They do not hide missing artifacts or
        # bypass calibrated/backtest gates.
        entry = registry_entry or self.registry_entry(key)
        total_rows = _int(entry.get("training_rows") or entry.get("trainingRows"))
        positive_rows = _int(entry.get("positive_rows") or entry.get("positiveRows"))
        negative_rows = _int(entry.get("negative_rows") or entry.get("negativeRows"))
        counts: dict[str, int] = {}
        if positive_rows:
            counts["1"] = positive_rows
        if negative_rows:
            counts["0"] = negative_rows
        return MarketTrainingStats(
            total_rows=total_rows,
            positive_rows=positive_rows,
            negative_rows=negative_rows,
            class_counts=counts,
            source="registry" if total_rows else "missing",
        )

    def registry_entry(self, market: str) -> dict[str, Any]:
        return self.artifact_repository.registry_entry(market)

    def load_registry(self) -> dict[str, Any]:
        return load_training_registry(self.settings.model_registry_path)

    def save_registry(self, registry: dict[str, Any]) -> dict[str, Any]:
        return save_training_registry(self.settings.model_registry_path, registry)

    def artifact_path(self, market: str, entry: dict[str, Any]) -> Path:
        return self.artifact_repository.resolve_entry(market, entry=entry).artifact_path or self.model_store.model_path_for_market(market).resolve()

    def metadata_path(self, market: str, artifact_path: Path, entry: dict[str, Any]) -> Path:
        return self.artifact_repository.resolve_entry(market, entry=entry).features_path or self.model_store.metadata_path_for_model(artifact_path).resolve()

    def backtest_gate(self, entry: dict[str, Any]) -> BacktestGate:
        backtest = entry.get("backtest") if isinstance(entry.get("backtest"), dict) else {}
        graded = _int(
            backtest.get("graded")
            or backtest.get("rows")
            or entry.get("backtest_rows")
            or entry.get("backtestRows")
        )
        return BacktestGate(
            graded=graded,
            brier_score=_float(backtest.get("brier_score") or backtest.get("brierScore") or entry.get("brier_score") or entry.get("brierScore")),
            log_loss=_float(backtest.get("log_loss") or backtest.get("logLoss") or entry.get("log_loss") or entry.get("logLoss")),
            roi_percent=_float(backtest.get("roi_percent") or backtest.get("roiPercent") or entry.get("backtest_roi") or entry.get("roiPercent")),
            source=str(backtest.get("source") or entry.get("backtest_source") or "registry"),
        )

    def market_status(self, market: str) -> dict[str, Any]:
        key = normalize_market_key(market)
        entry = self.registry_entry(key)
        stats = self.training_stats(key, registry_entry=entry)
        resolved_entry = self.artifact_repository.resolve_entry(key, entry=entry)
        artifact_path = resolved_entry.artifact_path or self.artifact_path(key, entry)
        metadata_path = resolved_entry.features_path or self.metadata_path(key, artifact_path, entry)
        verification = self.artifact_repository.verify_entry(key, entry=entry)
        artifact_exists = artifact_path.exists()
        metadata_exists = metadata_path.exists()
        hash_verified = bool(verification.get("ok"))
        registry_status = str(entry.get("status") or "research_only").strip().lower()
        calibrated = bool(entry.get("calibrated", False))
        backtest = self.backtest_gate(entry)

        readiness = registry_status if registry_status else "research_only"
        reason = "Market-specific model artifact available"
        warnings: list[str] = []

        if not hash_verified and resolved_entry.artifact_sha256:
            readiness = "not_ready"
            reason = "Model artifact hash verification failed"
        elif registry_status in DISABLED_STATUSES:
            readiness = "disabled"
            reason = "Market disabled in model registry"
        elif not artifact_exists:
            readiness = "not_ready"
            reason = "Missing market-specific model artifact"
        elif not metadata_exists:
            readiness = "not_ready"
            reason = "Missing model feature metadata"
        elif not stats.has_two_classes:
            readiness = "research_only"
            reason = "Training data has one class only"
        elif stats.total_rows < MIN_TRAINING_ROWS:
            readiness = "research_only"
            reason = f"Fewer than {MIN_TRAINING_ROWS} training rows"
        elif not calibrated:
            readiness = "experimental"
            reason = "Artifact exists, but calibration is not verified"
        elif registry_status in PRODUCTION_STATUSES and not backtest.ok_for_production:
            readiness = "experimental"
            reason = "Backtest gate has not cleared production thresholds"
        elif registry_status in PRODUCTION_STATUSES:
            readiness = registry_status
            reason = "Production gates cleared"
        else:
            readiness = registry_status if registry_status in {"research_only", "experimental"} else "experimental"
            reason = "Artifact available but not promoted to production"

        for error in verification.get("errors") or []:
            warnings.append(str(error))
        if stats.source != "csv":
            warnings.append(f"training counts came from {stats.source}; raw training CSV not available")
        if artifact_exists and not calibrated:
            warnings.append("calibration is not verified")
        if registry_status in PRODUCTION_STATUSES and not backtest.ok_for_production:
            warnings.append("production registry status blocked by backtest gate")

        production_eligible = (
            readiness in PRODUCTION_STATUSES
            and calibrated
            and artifact_exists
            and metadata_exists
            and stats.can_train
            and backtest.ok_for_production
        )

        return {
            "market": key,
            "trainingRows": stats.total_rows,
            "trainingSource": stats.source,
            "classCounts": stats.class_counts,
            "positiveRows": stats.positive_rows,
            "negativeRows": stats.negative_rows,
            "canTrain": stats.can_train,
            "modelTrained": artifact_exists and metadata_exists,
            "artifactExists": artifact_exists,
            "metadataExists": metadata_exists,
            "artifact": _public_path(self.settings.root_dir, artifact_path),
            "modelPath": _public_path(self.settings.root_dir, artifact_path),
            "metadataPath": _public_path(self.settings.root_dir, metadata_path),
            "registryStatus": registry_status,
            "status": readiness,
            "reason": reason,
            "warnings": warnings,
            "version": resolved_entry.version,
            "trainedAt": resolved_entry.trained_at or str(entry.get("trained_at") or entry.get("trainedAt") or ""),
            "trainingWindow": resolved_entry.training_window,
            "lastPromotedAt": resolved_entry.last_promoted_at,
            "calibrated": calibrated,
            "backtest": backtest.as_dict(),
            "productionEligible": production_eligible and hash_verified,
            "artifactSha256": resolved_entry.artifact_sha256,
            "featuresSha256": resolved_entry.features_sha256,
            "metricsSha256": resolved_entry.metrics_sha256,
            "trainingDataSha256": resolved_entry.training_data_sha256,
            "artifactHashPrefix": resolved_entry.artifact_hash_prefix,
            "hashVerified": hash_verified,
            "artifactVerification": _sanitize_verification_paths(verification, self.settings.root_dir),
            "knownLimitations": list(resolved_entry.known_limitations),
            "registryMetrics": resolved_entry.metrics,
        }

    def status_payload(self, markets: tuple[str, ...] = DEFAULT_MARKETS) -> dict[str, Any]:
        rows = [self.market_status(market) for market in markets]
        return {
            "status": "ok",
            "mode": "research" if self.settings.research_mode_default else "production",
            "markets": rows,
            "readyMarkets": [row["market"] for row in rows if row["canTrain"]],
            "notReadyMarkets": [row["market"] for row in rows if not row["canTrain"]],
            "trainedMarkets": [row["market"] for row in rows if row["modelTrained"]],
            "productionEligibleMarkets": [row["market"] for row in rows if row["productionEligible"]],
            "warnings": _dedupe([warning for row in rows for warning in row.get("warnings", [])]),
            "marketsWithHashIssues": [row["market"] for row in rows if row.get("artifactSha256") and not row.get("hashVerified")],
            "policy": {
                "requiresExactMarketArtifact": True,
                "genericFallbackAllowed": self.settings.allow_generic_prop_model_fallback,
                "minimumTrainingRows": MIN_TRAINING_ROWS,
                "minimumProductionBacktestRows": MIN_PRODUCTION_BACKTEST_ROWS,
                "maxProductionBrierScore": MAX_PRODUCTION_BRIER_SCORE,
                "maxProductionLogLoss": MAX_PRODUCTION_LOG_LOSS,
                "requiresCalibrationForProduction": True,
            },
        }

    def validate_promotion(
        self,
        market: str,
        target_status: str,
        *,
        source_status: str | None = None,
        model_key: str | None = None,
        allow_candidate_to_production: bool = False,
        allow_deprecated_to_production: bool = False,
    ) -> dict[str, Any]:
        result = self._validate_promotion_result(
            market,
            target_status,
            source_status=source_status,
            model_key=model_key,
            allow_candidate_to_production=allow_candidate_to_production,
            allow_deprecated_to_production=allow_deprecated_to_production,
        )
        return result.as_dict()

    def transition_model_status(
        self,
        market: str,
        target_status: str,
        *,
        source_status: str | None = None,
        model_key: str | None = None,
        allow_candidate_to_production: bool = False,
        allow_deprecated_to_production: bool = False,
    ) -> dict[str, Any]:
        key = normalize_market_key(market)
        target = str(target_status or "").strip().lower()
        validation = self._validate_promotion_result(
            key,
            target,
            source_status=source_status,
            model_key=model_key,
            allow_candidate_to_production=allow_candidate_to_production,
            allow_deprecated_to_production=allow_deprecated_to_production,
        )
        if not validation.allowed:
            return {
                "status": "rejected",
                "market": key,
                "target_status": target,
                "promotion": validation.as_dict(),
            }

        registry = self.load_registry()
        market_entry = registry.get(key)
        if not isinstance(market_entry, dict):
            market_entry = {}
        source = validation.source_status
        entry = _select_model_entry(market_entry, source_status=source, model_key=model_key)
        promoted = dict(entry)
        promoted["status"] = target
        promoted["market"] = key
        if target == "production":
            promoted["last_promoted_at"] = utc_now_iso()
        if model_key:
            promoted["selected_model"] = model_key
        market_entry[target] = promoted
        registry[key] = market_entry
        self.save_registry(registry)
        return {
            "status": "ok",
            "market": key,
            "source_status": source,
            "target_status": target,
            "promotion": validation.as_dict(),
        }

    def _validate_promotion_result(
        self,
        market: str,
        target_status: str,
        *,
        source_status: str | None = None,
        model_key: str | None = None,
        allow_candidate_to_production: bool = False,
        allow_deprecated_to_production: bool = False,
    ) -> PromotionValidationResult:
        key = normalize_market_key(market)
        target = str(target_status or "").strip().lower()
        registry = self.load_registry()
        raw_market = registry.get(key)
        market_entry = raw_market if isinstance(raw_market, dict) else {}
        source = str(source_status or ("shadow" if target == "production" else "candidate")).strip().lower()
        entry = _select_model_entry(market_entry, source_status=source, model_key=model_key)
        if not entry:
            entry = {"market": key, "status": source}
        entry.setdefault("status", source)
        entry.setdefault("market", key)
        resolved = self.artifact_repository.resolve_entry(key, stage=source, entry=entry)
        market_config = get_market_config(key) if is_supported_market(key) else None
        return validate_promotion_gate(
            market=key,
            entry=entry,
            target_status=target,
            source_status=source,
            market_config=market_config,
            artifact_path=resolved.artifact_path,
            feature_schema_path=resolved.features_path,
            allow_candidate_to_production=allow_candidate_to_production,
            allow_deprecated_to_production=allow_deprecated_to_production,
        )


def _read_csv_rows_cached(csv_store: Any, path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    reader = getattr(csv_store, "read_rows_cached", None)
    if callable(reader):
        return reader(path, max_age_seconds=60.0)
    return csv_store.read_rows(path)


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out


def load_training_registry(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    text = target.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Model registry must be a JSON object.")
    return payload


def save_training_registry(path: str | Path, registry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise ValueError("Model registry must be a JSON object.")
    _write_json_atomic(Path(path), registry)
    return registry


def write_training_registry_entries(
    path: str | Path,
    entries: list[dict[str, Any]],
    *,
    status: str,
) -> dict[str, Any]:
    selected_status = _validate_registry_status(status)
    if selected_status not in TRAINING_RUNNER_STATUSES:
        raise ValueError("Training runner can only write candidate or shadow registry entries.")
    registry_path = Path(path)
    registry = load_training_registry(registry_path)
    for entry in entries:
        market = normalize_market_key(str(entry.get("market") or ""))
        model_key = str(entry.get("model_key") or entry.get("modelKey") or "").strip()
        if not market or not model_key:
            continue
        entry_status = _validate_registry_status(str(entry.get("status") or selected_status))
        if entry_status != selected_status:
            raise ValueError("Registry entry status does not match the requested write status.")
        market_entry = registry.get(market)
        if not isinstance(market_entry, dict):
            market_entry = {}
        stage_entry = market_entry.get(selected_status)
        if not isinstance(stage_entry, dict):
            stage_entry = {}
        models = stage_entry.get("models")
        if not isinstance(models, dict):
            models = {}
        clean_entry = dict(entry)
        clean_entry["status"] = selected_status
        clean_entry["market"] = market
        clean_entry["model_key"] = model_key
        models[model_key] = clean_entry
        pointer = dict(clean_entry)
        pointer["models"] = models
        pointer["selected_model"] = model_key
        pointer["production_gated"] = True
        market_entry[selected_status] = pointer
        registry[market] = market_entry
    _write_json_atomic(registry_path, registry)
    return registry


def _validate_registry_status(status: str) -> str:
    text = str(status or "").strip().lower()
    if text not in SPRINT19_ALLOWED_MODEL_STATUSES:
        allowed = ", ".join(sorted(SPRINT19_ALLOWED_MODEL_STATUSES))
        raise ValueError(f"Unsupported model registry status {status!r}. Allowed statuses: {allowed}")
    return text


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _select_model_entry(market_entry: dict[str, Any], *, source_status: str, model_key: str | None = None) -> dict[str, Any]:
    stage_entry = market_entry.get(source_status)
    if not isinstance(stage_entry, dict):
        return {}
    models = stage_entry.get("models")
    if model_key and isinstance(models, dict) and isinstance(models.get(model_key), dict):
        selected = dict(models[model_key])
        selected.setdefault("selected_model", model_key)
        return selected
    selected_model = str(model_key or stage_entry.get("selected_model") or stage_entry.get("model_key") or "").strip()
    if selected_model and isinstance(models, dict) and isinstance(models.get(selected_model), dict):
        selected = dict(stage_entry)
        selected.update(dict(models[selected_model]))
        selected["selected_model"] = selected_model
        return selected
    return dict(stage_entry)


def _public_path(root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _sanitize_verification_paths(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(payload, default=str))
    for key in ("artifact", "features", "metrics"):
        value = sanitized.get(key)
        if isinstance(value, dict) and value.get("path"):
            value["path"] = _public_path(root, Path(str(value["path"])))
    entry = sanitized.get("entry")
    if isinstance(entry, dict):
        for key in ("artifactPath", "featuresPath", "metricsPath"):
            if entry.get(key):
                entry[key] = _public_path(root, Path(str(entry[key])))
    return sanitized
