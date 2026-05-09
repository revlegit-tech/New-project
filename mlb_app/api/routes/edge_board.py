from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container, get_edge_board_service, query_params
from mlb_app.api.models import EdgeBoardResponse
from mlb_app.api.routes._utils import board_contract
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.edge_board_service import EdgeBoardService

router = APIRouter(prefix="/api", tags=["board"])


@router.get("/edge-board", response_model=EdgeBoardResponse, name="native_edge_board")
async def edge_board(
    request: Request,
    service: Annotated[EdgeBoardService, Depends(get_edge_board_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.edge_board_timeout_seconds,
        route_name="/api/edge-board",
    )
    return board_contract(payload, "edge-board.v1")
