from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from mlb_app.api.dependencies import get_blocking_work_limiter, get_workflow_health_service
from mlb_app.api.models import WorkflowHealthResponse
from mlb_app.api.routes._utils import with_schema_version
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.workflow_health_service import WorkflowHealthService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("/health", response_model=WorkflowHealthResponse, name="native_workflow_health")
async def workflow_health(
    service: Annotated[WorkflowHealthService, Depends(get_workflow_health_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    payload = await limiter.run(service.payload, route_name="/api/workflows/health")
    return with_schema_version(payload, "workflow-health.v1")
