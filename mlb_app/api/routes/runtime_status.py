from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
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
