from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlb_app.services.model_registry_service import ModelRegistryService

PRODUCTION_STATUSES = {"production_candidate", "production"}
RESEARCH_STATUSES = {"disabled", "not_ready", "research_only", "experimental"}


@dataclass(frozen=True)
class MarketGate:
    market: str
    readiness: str
    label: str
    can_show_confident_pick: bool
    reason: str
    sample_size: int
    calibrated: bool
    latest_graded_date: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "readiness": self.readiness,
            "label": self.label,
            "canShowConfidentPick": self.can_show_confident_pick,
            "reason": self.reason,
            "sampleSize": self.sample_size,
            "calibrated": self.calibrated,
            "latestGradedDate": self.latest_graded_date,
        }


class ModelReadinessService:
    """Maps artifact/training status to product-facing readiness gates."""

    def __init__(self, registry_service: ModelRegistryService | None = None) -> None:
        self.registry_service = registry_service or ModelRegistryService()

    def gate_for_market(self, market: str, *, latest_graded_date: str = "") -> MarketGate:
        status = self.registry_service.market_status(market)
        readiness = str(status.get("status") or "not_ready")
        calibrated = bool(status.get("calibrated"))
        training_rows = int(status.get("trainingRows") or 0)

        if readiness == "disabled":
            label = "Disabled"
        elif readiness == "not_ready":
            label = "No model"
        elif readiness == "research_only":
            label = "Research only"
        elif readiness == "experimental":
            label = "Experimental"
        elif readiness == "production_candidate":
            label = "Production candidate"
        elif readiness == "production":
            label = "Production"
        else:
            label = readiness.replace("_", " ").title()

        can_show_confident = readiness in PRODUCTION_STATUSES and calibrated and bool(latest_graded_date)
        return MarketGate(
            market=str(status.get("market") or market),
            readiness=readiness,
            label=label,
            can_show_confident_pick=can_show_confident,
            reason=str(status.get("reason") or ""),
            sample_size=training_rows,
            calibrated=calibrated,
            latest_graded_date=latest_graded_date,
        )

    def payload(self, markets: list[str] | tuple[str, ...], *, latest_graded_date: str = "") -> dict[str, Any]:
        gates = [self.gate_for_market(market, latest_graded_date=latest_graded_date).as_dict() for market in markets]
        return {
            "markets": gates,
            "productionEligibleMarkets": [row["market"] for row in gates if row["canShowConfidentPick"]],
            "researchOnlyMarkets": [row["market"] for row in gates if not row["canShowConfidentPick"]],
        }
