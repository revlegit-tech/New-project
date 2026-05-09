from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_app_status_service, get_blocking_work_limiter, get_model_registry_service, query_params, request_id
from mlb_app.api.models import AppStatusResponse, PropMlStatusResponse
from mlb_app.api.routes._utils import with_schema_version
from mlb_app.services.app_status_service import AppStatusService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.model_registry_service import ModelRegistryService

router = APIRouter(prefix="/api", tags=["app"])


@router.get("/app/status", response_model=AppStatusResponse, name="native_app_status")
async def app_status(
    request: Request,
    service: Annotated[AppStatusService, Depends(get_app_status_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    query = query_params(request)
    rid = request_id(request)
    payload = await limiter.run(service.payload, query, request_id=rid, route_name="/api/app/status")
    return with_schema_version(payload, "app-status.v1")


@router.get("/prop-ml/status", response_model=PropMlStatusResponse, name="native_prop_ml_status")
async def prop_ml_status(
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    payload = await limiter.run(service.status_payload, route_name="/api/prop-ml/status")
    return with_schema_version(payload, "prop-ml-status.v1")
