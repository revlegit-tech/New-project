from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from fastapi import Request, Response
from pydantic import BaseModel

from mlb_app.api.models import EdgeBoardRow, ExposureSummaryPayload, ModelCardItem, PickItem, PropDetailPayload
from mlb_app.security.mutation import MutationEndpointSpec, enforce_mutation_security
from mlb_app.security.trusted_proxy import effective_client_ip_from_request

TModel = TypeVar("TModel", bound=BaseModel)


@dataclass(slots=True)
class _NativeHandlerCarrier:
    headers: Any


@dataclass(slots=True)
class _NativeMutationContext:
    handler: _NativeHandlerCarrier
    client_ip: str
    route_name: str


def apply_payload_status(payload: dict[str, Any], response: Response, *, schema_version: str | None = None) -> dict[str, Any]:
    result = dict(payload)
    status = result.pop("_status", None)
    if status is not None:
        response.status_code = int(status)
    if schema_version:
        result.setdefault("schemaVersion", schema_version)
    return result


def with_schema_version(payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
    result = dict(payload)
    result.setdefault("schemaVersion", schema_version)
    return result


def board_contract(payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
    result = with_schema_version(payload, schema_version)
    result["rows"] = _coerce_many(EdgeBoardRow, result.get("rows"))
    result["top"] = _coerce_many(EdgeBoardRow, result.get("top")) if "top" in result else result.get("top", [])
    return result


def model_cards_contract(payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
    result = with_schema_version(payload, schema_version)
    result["markets"] = _coerce_many(ModelCardItem, result.get("markets"))
    if isinstance(result.get("modelCard"), dict) and result["modelCard"]:
        result["modelCard"] = _coerce_one(ModelCardItem, result["modelCard"])
    return result


def picks_contract(payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
    result = with_schema_version(payload, schema_version)
    result["picks"] = _coerce_many(PickItem, result.get("picks"))
    if isinstance(result.get("pick"), dict):
        result["pick"] = _coerce_one(PickItem, result["pick"])
    if isinstance(result.get("exposure"), dict):
        result["exposure"] = _coerce_one(ExposureSummaryPayload, result["exposure"])
    return result


def exposure_contract(payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
    result = with_schema_version(payload, schema_version)
    if isinstance(result.get("exposure"), dict):
        result["exposure"] = _coerce_one(ExposureSummaryPayload, result["exposure"])
    return result


def prop_detail_contract(payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
    result = with_schema_version(payload, schema_version)
    if isinstance(result.get("detail"), dict):
        result["detail"] = _coerce_one(PropDetailPayload, result["detail"])
    return result


def _coerce_many(model: type[TModel], value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_coerce_one(model, item) for item in value if isinstance(item, dict)]


def _coerce_one(model: type[TModel], value: dict[str, Any]) -> dict[str, Any]:
    allowed = set(model.model_fields)
    filtered = {key: item for key, item in value.items() if key in allowed}
    return model.model_validate(filtered).model_dump(mode="json", exclude_none=True)


def enforce_native_mutation(
    request: Request,
    *,
    owner: str,
    risk: str = "medium",
    kind: str = "product_mutation",
    enabled: bool = True,
) -> None:
    spec = MutationEndpointSpec(owner=owner, risk=risk, kind=kind, enabled=enabled)
    context = _NativeMutationContext(
        handler=_NativeHandlerCarrier(headers=request.headers),
        client_ip=_client_ip(request),
        route_name=str(getattr(request.scope.get("route"), "name", kind) or kind),
    )
    enforce_mutation_security(context=context, spec=spec)


def _client_ip(request: Request) -> str:
    existing = getattr(request.state, "effective_client_ip", None)
    if existing:
        return str(existing)
    container = getattr(request.app.state, "container", None)
    trusted_proxy_cidrs = getattr(getattr(container, "settings", None), "trusted_proxy_cidrs", None)
    return effective_client_ip_from_request(request, trusted_proxy_cidrs)
