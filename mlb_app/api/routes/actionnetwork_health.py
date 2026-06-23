from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container
from mlb_app.container import AppContainer
from mlb_app.services.actionnetwork_health_service import ActionNetworkHealthService
from mlb_app.services.blocking_work import BlockingWorkLimiter

router = APIRouter(prefix="/api/actionnetwork", tags=["actionnetwork"])


@router.get("/snapshot-health", name="native_actionnetwork_snapshot_health")
async def actionnetwork_snapshot_health(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
) -> dict:
    service = ActionNetworkHealthService(container.settings)
    return await limiter.run(service.snapshot_health, date_text=date, route_name="/api/actionnetwork/snapshot-health")


@router.get("/label-eligibility", name="native_actionnetwork_label_eligibility")
async def actionnetwork_label_eligibility(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
) -> dict:
    service = ActionNetworkHealthService(container.settings)
    return await limiter.run(service.label_eligibility, date_text=date, route_name="/api/actionnetwork/label-eligibility")


@router.get("/trust", name="native_actionnetwork_trust")
async def actionnetwork_trust(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
) -> dict:
    service = ActionNetworkHealthService(container.settings)
    return await limiter.run(service.trust_summary, date_text=date, route_name="/api/actionnetwork/trust")
