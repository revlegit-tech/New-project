from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import get_blocking_work_limiter, get_prediction_audit_service, query_params
from mlb_app.api.models import PredictionEventsResponse
from mlb_app.api.routes._utils import apply_payload_status, enforce_native_mutation, with_schema_version
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.prediction_audit_service import PredictionAuditService

router = APIRouter(prefix="/api", tags=["prediction-audit"])


@router.get("/prediction-events", response_model=PredictionEventsResponse, name="native_prediction_events")
async def prediction_events(
    request: Request,
    service: Annotated[PredictionAuditService, Depends(get_prediction_audit_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    payload = await limiter.run(service.payload, query_params(request), route_name="/api/predictions/events")
    return with_schema_version(payload, "prediction-events.v1")


@router.post("/prediction-events", response_model=PredictionEventsResponse, name="native_record_prediction_event")
async def record_prediction_event(
    request: Request,
    response: Response,
    body: dict[str, Any],
    service: Annotated[PredictionAuditService, Depends(get_prediction_audit_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="model_audit", risk="medium", kind="prediction_event_write")
    payload = await limiter.run(service.record, body, route_name="POST /api/prediction-events")
    return apply_payload_status(payload, response, schema_version="prediction-events.v1")
