from __future__ import annotations

from dataclasses import dataclass, replace
from http import HTTPStatus
from typing import Any, Callable

from .http import ApiError, RequestContext, error_payload, json_response
from .middleware import AccessLogEvent, log_access, monotonic_ms
from .security.mutation import MutationEndpointSpec, MutationSecurityError, enforce_mutation_security

Handler = Callable[[RequestContext], Any]


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: Handler
    name: str = ""
    mutation: MutationEndpointSpec | None = None


class Router:
    """Explicit route table with one observability/security boundary."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], Route] = {}

    def add(
        self,
        method: str,
        path: str,
        handler: Handler,
        *,
        name: str = "",
        mutation: bool = False,
        mutation_owner: str = "",
        mutation_risk: str = "medium",
        mutation_kind: str = "product_mutation",
        mutation_enabled: bool = True,
    ) -> None:
        key = (method.upper(), path)
        if key in self._routes:
            raise ValueError(f"Duplicate route registered for {method.upper()} {path}")
        spec = None
        if mutation:
            spec = MutationEndpointSpec(owner=mutation_owner or "unassigned", risk=mutation_risk, kind=mutation_kind, enabled=mutation_enabled)
        self._routes[key] = Route(method.upper(), path, handler, name or f"{method.upper()} {path}", spec)

    def route(self, method: str, path: str, **metadata: Any) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self.add(method, path, handler, **metadata)
            return handler
        return decorator

    def dispatch(self, context: RequestContext) -> bool:
        route = self._routes.get((context.method.upper(), context.path))
        if route is None:
            return False

        request_context = replace(context, route_name=route.name)
        status_int = int(HTTPStatus.OK)
        rate_limited = False
        try:
            enforce_mutation_security(context=request_context, spec=route.mutation)
            payload = route.handler(request_context)
            status_int = int(payload.pop("_status", HTTPStatus.OK)) if isinstance(payload, dict) else int(HTTPStatus.OK)
            json_response(request_context.handler, payload, status_int)
        except MutationSecurityError as error:
            status_int = error.status
            rate_limited = error.code == "rate_limited"
            json_response(
                request_context.handler,
                {"status": "error", "code": error.code, "error": error.message},
                status_int,
                extra_headers={"Retry-After": str(error.retry_after)} if error.retry_after is not None else None,
            )
        except Exception as error:  # noqa: BLE001 - central safe API boundary
            payload, status_int = error_payload(error)
            json_response(request_context.handler, payload, status_int)
        finally:
            log_access(
                AccessLogEvent(
                    request_id=request_context.request_id or str(getattr(request_context.handler, "request_id", "")),
                    method=request_context.method,
                    path=request_context.path,
                    status=status_int,
                    elapsed_ms=monotonic_ms(request_context.started_at or getattr(request_context.handler, "request_started_at", 0.0)),
                    client_ip=request_context.client_ip,
                    route=route.name,
                    mutation=route.mutation is not None,
                    rate_limited=rate_limited,
                    auth_mode=route.mutation.kind if route.mutation is not None else None,
                )
            )
        return True

    def require(self, method: str, path: str) -> Route:
        try:
            return self._routes[(method.upper(), path)]
        except KeyError as error:
            raise ApiError(HTTPStatus.NOT_FOUND, "Route not found", code="route_not_found") from error

    @property
    def routes(self) -> tuple[Route, ...]:
        return tuple(self._routes.values())

    @property
    def mutation_routes(self) -> tuple[Route, ...]:
        return tuple(route for route in self._routes.values() if route.mutation is not None)
