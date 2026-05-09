from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_app_status_service, query_params, request_id
from mlb_app.api.models import AppStatusResponse
from mlb_app.services.app_status_service import AppStatusService

router = APIRouter(prefix="/api/app", tags=["app"])


@router.get("/status", response_model=AppStatusResponse, name="native_app_status")
async def app_status(
    request: Request,
    service: Annotated[AppStatusService, Depends(get_app_status_service)],
) -> dict:
    query = query_params(request)
    rid = request_id(request)
    return await asyncio.to_thread(service.payload, query, request_id=rid)
