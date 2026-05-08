from __future__ import annotations

from typing import Any

from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.playerboard_service import PlayerboardService
from mlb_app.services.product_state_service import ProductStateService
from mlb_app.services.workflow_health_service import WorkflowHealthService
from mlb_app.schemas.app_status import build_app_status_payload, validate_app_status_payload


class AppStatusService:
    def __init__(
        self,
        *,
        playerboard_service: PlayerboardService | None = None,
        grading_service: GradingStateService | None = None,
        model_registry_service: ModelRegistryService | None = None,
        workflow_service: WorkflowHealthService | None = None,
        product_state_service: ProductStateService | None = None,
    ) -> None:
        self.grading_service = grading_service or GradingStateService()
        self.product_state_service = product_state_service or ProductStateService()
        self.model_registry_service = model_registry_service or ModelRegistryService()
        self.workflow_service = workflow_service or WorkflowHealthService()
        self.playerboard_service = playerboard_service or PlayerboardService(
            grading_service=self.grading_service,
            product_state_service=self.product_state_service,
        )

    def payload(self, query: dict[str, list[str]] | None = None, *, request_id: str = "") -> dict[str, Any]:
        query = query or {}
        season = int((query.get("season") or ["2026"])[0])
        playerboard = self.playerboard_service.health_payload({"season": [str(season)]})
        board_date = str(playerboard.get("latestAvailableDate") or playerboard.get("date") or "")
        grading = self.grading_service.payload({"date": [board_date]} if board_date else {})
        workflows = self.workflow_service.payload()
        model_status = self.model_registry_service.status_payload()
        product_state = self.product_state_service.payload(
            production_eligible_markets=len(model_status.get("productionEligibleMarkets", [])),
            grading_ok=bool(grading.get("ok")),
        )

        payload = build_app_status_payload(
            season=season,
            playerboard=playerboard,
            grading=grading,
            workflows=workflows,
            model_status=model_status,
            product_state=product_state,
            request_id=request_id,
        )
        contract_errors = validate_app_status_payload(payload)
        if contract_errors:
            payload["ok"] = False
            payload.setdefault("warnings", []).append("App-status contract validation failed.")
            payload["contractErrors"] = contract_errors
        return payload
