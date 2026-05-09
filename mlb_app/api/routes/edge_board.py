from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_edge_board_service, query_params
from mlb_app.api.models import EdgeBoardResponse
from mlb_app.services.edge_board_service import EdgeBoardService

router = APIRouter(prefix="/api", tags=["board"])


@router.get("/edge-board", response_model=EdgeBoardResponse, name="native_edge_board")
async def edge_board(
    request: Request,
    service: Annotated[EdgeBoardService, Depends(get_edge_board_service)],
) -> dict:
    return await asyncio.to_thread(service.payload, query_params(request))
