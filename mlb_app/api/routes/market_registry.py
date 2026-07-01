from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container, get_mlb_market_registry_service, query_params
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.mlb_market_registry_service import MLBMarketRegistryService

router = APIRouter(prefix="/api/mlb", tags=["market-registry"])


@router.get("/market-registry", name="mlb_market_registry")
async def market_registry(
    request: Request,
    service: Annotated[MLBMarketRegistryService, Depends(get_mlb_market_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    return await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/mlb/market-registry",
    )
