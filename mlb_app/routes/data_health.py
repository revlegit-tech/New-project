from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.data_health_dashboard_service import DataHealthDashboardService
from mlb_app.services.data_health_service import DataHealthService
from mlb_app.services.grading_state_service import GradingStateService


def data_health(context: RequestContext) -> dict[str, Any]:
    return DataHealthService().payload(context.query)


def data_health_dashboard(context: RequestContext) -> dict[str, Any]:
    return DataHealthDashboardService().payload(context.query)


def grading_health(context: RequestContext) -> dict[str, Any]:
    return GradingStateService().payload(context.query)
