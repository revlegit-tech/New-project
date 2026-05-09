from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_playerboard_service, query_params
from mlb_app.api.models import PlayerboardHealthResponse, PlayerboardResponse
from mlb_app.services.playerboard_service import PlayerboardService

router = APIRouter(prefix="/api/playerboard", tags=["playerboard"])


@router.get("", response_model=PlayerboardResponse, name="native_playerboard")
async def playerboard(
    request: Request,
    service: Annotated[PlayerboardService, Depends(get_playerboard_service)],
) -> dict:
    return await asyncio.to_thread(service.board_payload, query_params(request))


@router.get("/health", response_model=PlayerboardHealthResponse, name="native_playerboard_health")
async def playerboard_health(
    request: Request,
    service: Annotated[PlayerboardService, Depends(get_playerboard_service)],
) -> dict:
    return await asyncio.to_thread(service.health_payload, query_params(request))
