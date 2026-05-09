from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container, get_playerboard_service, query_params
from mlb_app.api.models import PlayerboardHealthResponse, PlayerboardResponse
from mlb_app.api.routes._utils import board_contract, with_schema_version
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.playerboard_service import PlayerboardService

router = APIRouter(prefix="/api/playerboard", tags=["playerboard"])


@router.get("", response_model=PlayerboardResponse, name="native_playerboard")
async def playerboard(
    request: Request,
    service: Annotated[PlayerboardService, Depends(get_playerboard_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.board_payload,
        query_params(request),
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/playerboard",
    )
    return board_contract(payload, "playerboard.v1")


@router.get("/health", response_model=PlayerboardHealthResponse, name="native_playerboard_health")
async def playerboard_health(
    request: Request,
    service: Annotated[PlayerboardService, Depends(get_playerboard_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.health_payload,
        query_params(request),
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/playerboard/health",
    )
    return with_schema_version(payload, "playerboard-health.v1")
