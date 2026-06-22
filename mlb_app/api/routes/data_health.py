from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import (
    get_blocking_work_limiter,
    get_container,
    get_data_health_dashboard_service,
    get_data_health_service,
    get_data_status_service,
    get_grading_service,
    query_params,
)
from mlb_app.api.models import DataHealthDashboardResponse, DataHealthResponse, DataStatusResponse, GradingHealthResponse
from mlb_app.api.routes._utils import with_schema_version
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.data_health_dashboard_service import DataHealthDashboardService
from mlb_app.services.data_health_service import DataHealthService
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.grading_state_service import GradingStateService

router = APIRouter(prefix="/api", tags=["data-health"])


@router.get("/data-health", response_model=DataHealthResponse, name="native_data_health")
async def data_health(
    request: Request,
    service: Annotated[DataHealthService, Depends(get_data_health_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/data-health",
    )
    return with_schema_version(payload, "data-health.v1")


@router.get("/data-health/dashboard", response_model=DataHealthDashboardResponse, name="native_data_health_dashboard")
async def data_health_dashboard(
    request: Request,
    service: Annotated[DataHealthDashboardService, Depends(get_data_health_dashboard_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/data-health/dashboard",
    )
    return with_schema_version(payload, "data-health-dashboard.v1")


@router.get("/data/status", response_model=DataStatusResponse, name="native_data_status")
async def data_status(
    request: Request,
    service: Annotated[DataStatusService, Depends(get_data_status_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/data/status",
    )
    return with_schema_version(payload, "data-status.v1")


@router.get("/grading/health", response_model=GradingHealthResponse, name="native_grading_health")
async def grading_health(
    request: Request,
    service: Annotated[GradingStateService, Depends(get_grading_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/grading/health",
    )
    return with_schema_version(payload, "grading-health.v1")
