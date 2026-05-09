from __future__ import annotations

from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.alert_service import AlertService
from mlb_app.services.board_cache import BoardCache
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
        alert_service: AlertService | None = None,
        board_cache: BoardCache | None = None,
        settings: Settings = default_settings,
    ) -> None:
        self.settings = settings
        self.grading_service = grading_service or GradingStateService(settings=self.settings)
        self.product_state_service = product_state_service or ProductStateService(settings=self.settings)
        self.model_registry_service = model_registry_service or ModelRegistryService(settings=self.settings)
        self.workflow_service = workflow_service or WorkflowHealthService(settings=self.settings)
        self.alert_service = alert_service or AlertService()
        self.board_cache = board_cache
        self.playerboard_service = playerboard_service or PlayerboardService(
            grading_service=self.grading_service,
            product_state_service=self.product_state_service,
            settings=self.settings,
        )

    def payload(self, query: dict[str, list[str]] | None = None, *, request_id: str = "") -> dict[str, Any]:
        query = query or {}
        season = self.settings.season_from_query(query)
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
        snapshot_age = _snapshot_age_seconds(playerboard)
        payload["snapshotAgeSeconds"] = snapshot_age
        payload["boardCacheStatus"] = self.board_cache.status() if self.board_cache is not None else {}
        if isinstance(snapshot_age, (int, float)) and snapshot_age > 300:
            payload.setdefault("warnings", []).append("stale_snapshot")
            payload["ok"] = False

        contract_errors = validate_app_status_payload(payload)
        if contract_errors:
            payload["ok"] = False
            payload.setdefault("warnings", []).append("App-status contract validation failed.")
            payload["contractErrors"] = contract_errors
        alert_payload = self.alert_service.payload(app_status=payload, model_status=model_status)
        payload["alerts"] = alert_payload.get("alerts", [])
        payload["alertCount"] = alert_payload.get("alertCount", 0)
        payload["observability"] = {"alerts": alert_payload}
        return payload


def _snapshot_age_seconds(playerboard: dict[str, Any]) -> float | None:
    freshness = playerboard.get("freshness") if isinstance(playerboard.get("freshness"), dict) else {}
    age = freshness.get("ageSeconds")
    if isinstance(age, (int, float)):
        return float(age)
    return None
