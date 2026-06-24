from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container
from mlb_app.api.models import CollectorCheckResponse
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.collector_verification_service import CollectorVerificationService
from mlb_app.services.data_freshness_service import DataFreshnessService
from mlb_app.services.runtime_status_service import RuntimeStatusService

router = APIRouter(prefix="/api", tags=["runtime"])


@router.get("/runtime/status", name="native_runtime_status")
async def runtime_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    service = RuntimeStatusService(container.settings)
    return await limiter.run(service.runtime_status, route_name="/api/runtime/status")


@router.get("/runtime/collector-check", response_model=CollectorCheckResponse, name="native_runtime_collector_check")
async def collector_check(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
) -> dict:
    service = CollectorVerificationService(
        settings=container.settings,
        board_snapshot_repository=container.board_snapshot_repository,
        edge_board_service=container.edge_board_service,
        runtime_status_service=RuntimeStatusService(container.settings),
    )
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.payload,
        date_label=date,
        season=selected_season,
        route_name="/api/runtime/collector-check",
    )


@router.get("/workflow/status", name="native_workflow_status")
async def workflow_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    service = RuntimeStatusService(container.settings)
    return await limiter.run(service.workflow_status, route_name="/api/workflow/status")


@router.get("/data-freshness", name="native_data_freshness")
async def data_freshness(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
) -> dict:
    service = DataFreshnessService(container.settings)
    return await limiter.run(service.payload, date, route_name="/api/data-freshness")
