from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.csv_store import CsvStore
from mlb_app.repositories.model_store import ModelStore, normalize_market_key

DEFAULT_MARKETS: tuple[str, ...] = (
    "pitcher_strikeouts",
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
)

MIN_TRAINING_ROWS = 25


@dataclass(frozen=True)
class MarketTrainingStats:
    total_rows: int
    positive_rows: int
    negative_rows: int
    class_counts: dict[str, int]

    @property
    def has_two_classes(self) -> bool:
        return self.positive_rows > 0 and self.negative_rows > 0

    @property
    def can_train(self) -> bool:
        return self.total_rows >= MIN_TRAINING_ROWS and self.has_two_classes


class ModelRegistryService:
    """Single source of truth for production-facing market readiness.

    Exact market artifacts are required. A generic prop model may still exist for
    local experiments, but this service never reports a market as trained unless
    the market-specific artifact exists.
    """

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        csv_store: CsvStore | None = None,
        model_store: ModelStore | None = None,
    ) -> None:
        self.settings = settings
        self.csv_store = csv_store or CsvStore()
        self.model_store = model_store or ModelStore(settings.model_dir)

    def training_stats(self, market: str) -> MarketTrainingStats:
        key = normalize_market_key(market)
        path = self.settings.data_dir / "training" / f"{key}_training.csv"
        rows = _read_csv_rows_cached(self.csv_store, path)
        counts: Counter[str] = Counter()
        for row in rows:
            value = str(row.get("over", "")).strip()
            if value in {"0", "1"}:
                counts[value] += 1
        return MarketTrainingStats(
            total_rows=len(rows),
            positive_rows=counts.get("1", 0),
            negative_rows=counts.get("0", 0),
            class_counts=dict(counts),
        )

    def registry_entry(self, market: str) -> dict[str, Any]:
        registry = self.model_store.load_registry(self.settings.model_registry_path)
        raw = registry.get(normalize_market_key(market), {})
        return raw if isinstance(raw, dict) else {}

    def artifact_path(self, market: str, entry: dict[str, Any]) -> Path:
        artifact = str(entry.get("artifact") or "").strip()
        if artifact:
            path = Path(artifact)
            return path if path.is_absolute() else (self.settings.root_dir / path).resolve()
        return self.model_store.model_path_for_market(market).resolve()

    def market_status(self, market: str) -> dict[str, Any]:
        key = normalize_market_key(market)
        entry = self.registry_entry(key)
        stats = self.training_stats(key)
        artifact_path = self.artifact_path(key, entry)
        metadata_path = self.model_store.metadata_path_for_model(artifact_path)
        artifact_exists = artifact_path.exists()
        metadata_exists = metadata_path.exists()
        registry_status = str(entry.get("status") or "research").strip().lower()
        calibrated = bool(entry.get("calibrated", False))

        if not artifact_exists:
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
        elif registry_status in {"disabled", "blocked"}:
            readiness = "disabled"
            reason = "Market disabled in model registry"
        else:
            readiness = registry_status if registry_status else "experimental"
            reason = "Market-specific model artifact available"

        return {
            "market": key,
            "trainingRows": stats.total_rows,
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
            "status": readiness,
            "reason": reason,
            "trainedAt": str(entry.get("trained_at") or ""),
            "calibrated": calibrated,
            "productionEligible": readiness in {"production_candidate", "production"} and calibrated,
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
            "policy": {
                "requiresExactMarketArtifact": True,
                "genericFallbackAllowed": self.settings.allow_generic_prop_model_fallback,
                "minimumTrainingRows": MIN_TRAINING_ROWS,
            },
        }


def _read_csv_rows_cached(csv_store: Any, path: Path) -> list[dict[str, str]]:
    reader = getattr(csv_store, "read_rows_cached", None)
    if callable(reader):
        return reader(path, max_age_seconds=60.0)
    return csv_store.read_rows(path)
