from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
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
            "artifact": str(artifact_path),
            "modelPath": str(artifact_path),
            "metadataPath": str(metadata_path),
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
            "artifactVerification": verification,
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
