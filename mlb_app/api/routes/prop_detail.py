from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container, get_prop_detail_service, query_params
from mlb_app.api.models import PropDetailResponse
from mlb_app.api.routes._utils import prop_detail_contract
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.prop_detail_service import PropDetailService

router = APIRouter(prefix="/api", tags=["props"])


@router.get("/prop-detail", response_model=PropDetailResponse, name="native_prop_detail")
async def prop_detail(
    request: Request,
    service: Annotated[PropDetailService, Depends(get_prop_detail_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    payload = await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.prop_detail_timeout_seconds,
        route_name="/api/prop-detail",
    )
    return prop_detail_contract(payload, "prop-detail.v1")
