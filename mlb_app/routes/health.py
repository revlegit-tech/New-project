from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.app_status_service import AppStatusService
from mlb_app.services.model_registry_service import ModelRegistryService


def app_status(context: RequestContext) -> dict[str, Any]:
    return AppStatusService().payload(context.query, request_id=context.request_id)


def prop_ml_status(context: RequestContext) -> dict[str, Any]:
    return ModelRegistryService().status_payload()
