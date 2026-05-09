from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_alert_service, get_app_status_service, get_blocking_work_limiter, get_metrics_registry, get_model_registry_service, query_params, request_id
from mlb_app.api.models import ObservabilityMetricsResponse
from mlb_app.observability.metrics import MetricsRegistry
from mlb_app.services.alert_service import AlertService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.app_status_service import AppStatusService
from mlb_app.services.model_registry_service import ModelRegistryService

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/metrics", response_model=ObservabilityMetricsResponse, name="native_observability_metrics")
async def metrics(
    registry: Annotated[MetricsRegistry, Depends(get_metrics_registry)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    return await limiter.run(registry.snapshot, route_name="/api/observability/metrics")


@router.get("/alerts", name="native_observability_alerts")
async def alerts(
    request: Request,
    alert_service: Annotated[AlertService, Depends(get_alert_service)],
    status_service: Annotated[AppStatusService, Depends(get_app_status_service)],
    model_registry_service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    def _payload() -> dict[str, Any]:
        status_payload = status_service.payload(query_params(request), request_id=request_id(request))
        model_status = model_registry_service.status_payload()
        return alert_service.payload(app_status=status_payload, model_status=model_status)

    return await limiter.run(_payload, route_name="/api/observability/alerts")
