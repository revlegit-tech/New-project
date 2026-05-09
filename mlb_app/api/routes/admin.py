from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import get_blocking_work_limiter, get_propline_props_service
from mlb_app.api.models import ProplineSyncResponse
from mlb_app.api.routes._utils import apply_payload_status, enforce_native_mutation
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.propline_props_service import PROPLINE_MARKETS, PropLineSyncRequest, ProplinePropsService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _first_query_or_body(request: Request, body: dict[str, Any], key: str, fallback: str = "") -> str:
    value = request.query_params.get(key)
    if value is not None:
        return str(value)
    candidate = body.get(key, fallback)
    return str(candidate if candidate is not None else fallback)


def _boolish(value: str, *, default: bool = True) -> bool:
    if value == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _markets(request: Request, body: dict[str, Any]) -> tuple[str, ...]:
    if isinstance(body.get("markets"), list):
        values = tuple(str(item).strip() for item in body["markets"] if str(item).strip())
        return values or tuple(PROPLINE_MARKETS)
    raw = request.query_params.get("markets")
    if raw is None:
        raw = str(body.get("markets", "") or "")
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or tuple(PROPLINE_MARKETS)


def _intish(value: str, *, default: int = 0) -> int:
    try:
        return int(value.strip()) if value.strip() else default
    except ValueError:
        return default


@router.post("/propline/props/sync", response_model=ProplineSyncResponse, name="native_admin_sync_propline_props")
async def sync_propline_props(
    request: Request,
    response: Response,
    service: Annotated[ProplinePropsService, Depends(get_propline_props_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="data_ops", risk="high", kind="external_paid_api_sync")
    payload = body or {}
    sync_request = PropLineSyncRequest(
        date=_first_query_or_body(request, payload, "date"),
        sport=_first_query_or_body(request, payload, "sport", "baseball_mlb") or "baseball_mlb",
        markets=_markets(request, payload),
        save=_boolish(_first_query_or_body(request, payload, "save", "1")),
        snapshot=_boolish(_first_query_or_body(request, payload, "snapshot", "1")),
        max_events=_intish(_first_query_or_body(request, payload, "maxEvents", "0")),
    )
    result = await limiter.run(service.sync, sync_request, timeout_seconds=120.0, route_name="POST /api/admin/propline/props/sync")
    return apply_payload_status(result, response, schema_version="propline-sync.v1")
