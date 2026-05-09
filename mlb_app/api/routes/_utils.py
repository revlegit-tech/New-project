from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from fastapi import Request, Response

from mlb_app.security.mutation import MutationEndpointSpec, MutationSecurityError, enforce_mutation_security


@dataclass(slots=True)
class _NativeHandlerCarrier:
    headers: Any


@dataclass(slots=True)
class _NativeMutationContext:
    handler: _NativeHandlerCarrier
    client_ip: str
    route_name: str


def apply_payload_status(payload: dict[str, Any], response: Response) -> dict[str, Any]:
    result = dict(payload)
    status = result.pop("_status", None)
    if status is not None:
        response.status_code = int(status)
    return result


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
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
