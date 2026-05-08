from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.workflow_health_service import WorkflowHealthService


def workflow_health(_context: RequestContext) -> dict[str, Any]:
    return WorkflowHealthService().payload()
