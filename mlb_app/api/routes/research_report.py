from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container, get_research_report_service, query_params
from mlb_app.api.models import ResearchReportResponse
from mlb_app.container import AppContainer
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.edge_report_service import EdgeReportService

router = APIRouter(prefix="/api", tags=["research-report"])


@router.get("/research/report", response_model=ResearchReportResponse, name="native_research_report")
async def research_report(
    request: Request,
    service: Annotated[EdgeReportService, Depends(get_research_report_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    return await limiter.run(
        service.payload,
        query_params(request),
        timeout_seconds=container.settings.edge_board_timeout_seconds,
        route_name="/api/research/report",
    )
