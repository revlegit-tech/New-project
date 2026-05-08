from __future__ import annotations

from datetime import datetime
from typing import Any

from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.product_state_service import ProductStateService


class DataHealthService:
    def __init__(
        self,
        *,
        grading_service: GradingStateService | None = None,
        product_state_service: ProductStateService | None = None,
    ) -> None:
        self.grading_service = grading_service or GradingStateService()
        self.product_state_service = product_state_service or ProductStateService()

    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        from data_health import data_health_payload

        date_label = str((query.get("date") or [datetime.now().strftime("%Y-%m-%d")])[0] or "")
        payload = data_health_payload(date_label)
        grading = self.grading_service.payload({"date": [date_label]})
        product_state = self.product_state_service.payload(grading_ok=bool(grading.get("ok")))
        if isinstance(payload, dict):
            enriched = dict(payload)
            enriched.setdefault("grading", grading)
            enriched.setdefault("productState", product_state)
            enriched.setdefault("latestFullyGradedDate", grading.get("latestFullyGradedDate", ""))
            enriched.setdefault("trust", {
                "mode": product_state["state"],
                "banner": product_state["label"],
                "message": product_state["message"],
                "latestFullyGradedDate": grading.get("latestFullyGradedDate", ""),
            })
            return enriched
        return payload
