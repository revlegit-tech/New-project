from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.schemas.common import ProductState


@dataclass(frozen=True)
class ProductStatePayload:
    state: ProductState
    label: str
    severity: str
    message: str
    research_mode: bool
    allowed_decision_labels: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "productState": self.state.value,
            "label": self.label,
            "severity": self.severity,
            "message": self.message,
            "researchMode": self.research_mode,
            "allowedDecisionLabels": list(self.allowed_decision_labels),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }


class ProductStateService:
    """Central product-state gate for bettor-facing trust language.

    The default is intentionally conservative. Markets can become production
    candidates later, but the overall product surface stays in Research Mode
    until model readiness, grading freshness, and calibration gates are wired to
    an explicit promotion workflow.
    """

    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def current(self, *, production_eligible_markets: int = 0, grading_ok: bool = False) -> ProductStatePayload:
        if self.settings.research_mode_default:
            return ProductStatePayload(
                state=ProductState.RESEARCH,
                label="Research Mode",
                severity="warning",
                message=(
                    "Model outputs are experimental. Use this board for research, "
                    "not blind tailing or automated betting."
                ),
                research_mode=True,
                allowed_decision_labels=("No bet", "Watchlist", "Model lean"),
            )

        if production_eligible_markets > 0 and grading_ok:
            return ProductStatePayload(
                state=ProductState.PRODUCTION_TRACKED,
                label="Production Tracked",
                severity="success",
                message="Production markets have model cards, grading history, and calibration gates enabled.",
                research_mode=False,
                allowed_decision_labels=("No bet", "Watchlist", "Potential edge"),
            )

        return ProductStatePayload(
            state=ProductState.EXPERIMENTAL,
            label="Experimental Model",
            severity="caution",
            message="Some models are available, but market-level readiness gates are still experimental.",
            research_mode=True,
            allowed_decision_labels=("No bet", "Watchlist", "Model lean"),
        )

    def payload(self, **kwargs: Any) -> dict[str, Any]:
        return self.current(**kwargs).as_dict()
