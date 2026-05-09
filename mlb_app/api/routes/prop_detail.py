from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_prop_detail_service, query_params
from mlb_app.api.models import PropDetailResponse
from mlb_app.services.prop_detail_service import PropDetailService

router = APIRouter(prefix="/api", tags=["props"])


@router.get("/prop-detail", response_model=PropDetailResponse, name="native_prop_detail")
async def prop_detail(
    request: Request,
    service: Annotated[PropDetailService, Depends(get_prop_detail_service)],
) -> dict:
    return await asyncio.to_thread(service.payload, query_params(request))
