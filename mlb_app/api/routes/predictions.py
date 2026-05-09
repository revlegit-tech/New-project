from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import get_prediction_audit_service, query_params
from mlb_app.api.models import PredictionEventsResponse
from mlb_app.api.routes._utils import apply_payload_status, enforce_native_mutation
from mlb_app.services.prediction_audit_service import PredictionAuditService

router = APIRouter(prefix="/api", tags=["prediction-audit"])


@router.get("/prediction-events", response_model=PredictionEventsResponse, name="native_prediction_events")
async def prediction_events(
    request: Request,
    service: Annotated[PredictionAuditService, Depends(get_prediction_audit_service)],
) -> dict[str, Any]:
    return await asyncio.to_thread(service.payload, query_params(request))


@router.post("/prediction-events", response_model=PredictionEventsResponse, name="native_record_prediction_event")
async def record_prediction_event(
    request: Request,
    response: Response,
    body: dict[str, Any],
    service: Annotated[PredictionAuditService, Depends(get_prediction_audit_service)],
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="model_audit", risk="medium", kind="prediction_event_write")
    payload = await asyncio.to_thread(service.record, body)
    return apply_payload_status(payload, response)
