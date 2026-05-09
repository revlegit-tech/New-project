from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from mlb_app.middleware import AccessLogEvent, log_access, monotonic_ms, normalize_request_id


class RequestMetadataMiddleware(BaseHTTPMiddleware):
    """Attach request ids to native FastAPI requests and log access records."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started_at = time.perf_counter()
        request_id = normalize_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        request.state.started_at = started_at
        response = await call_next(request)
        response.headers.setdefault("X-Request-Id", request_id)
        route_name = _route_name(request)
        elapsed_ms = monotonic_ms(started_at)
        cache_hit = _cache_hit(request, response)
        _record_request_metrics(request, response, elapsed_ms, route_name, cache_hit)
        log_access(
            AccessLogEvent(
                request_id=request_id,
                method=request.method.upper(),
                path=request.url.path,
                status=response.status_code,
                elapsed_ms=elapsed_ms,
                client_ip=_client_ip(request),
                route=route_name,
                cache_hit=cache_hit,
            )
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline browser hardening headers to API and static responses."""

    def __init__(self, app: Any, *, csp_report_only: bool = True) -> None:
        super().__init__(app)
        self.csp_report_only = csp_report_only

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        csp_value = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'"
        )
        csp_header = "Content-Security-Policy-Report-Only" if self.csp_report_only else "Content-Security-Policy"
        response.headers.setdefault(csp_header, csp_value)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), fullscreen=(self)",
        )
        return response


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


def _route_name(request: Request) -> str:
    route = request.scope.get("route")
    name = getattr(route, "name", "") if route is not None else ""
    return str(name or request.url.path)


def _cache_hit(request: Request, response: Response) -> bool | None:
    value = getattr(request.state, "cache_hit", None)
    if isinstance(value, bool):
        return value
    header = response.headers.get("X-Cache-Hit")
    if header:
        return header.lower() in {"1", "true", "yes", "hit"}
    return None


def _record_request_metrics(request: Request, response: Response, elapsed_ms: float, route_name: str, cache_hit: bool | None) -> None:
    try:
        container = getattr(request.app.state, "container", None)
        registry = getattr(container, "metrics", None)
        if registry is None:
            from mlb_app.observability.metrics import default_registry

            registry = default_registry()
        labels = {
            "method": request.method.upper(),
            "route": route_name,
            "status": response.status_code,
        }
        registry.increment("http_requests_total", labels=labels)
        registry.observe("http_request_latency_ms", elapsed_ms, labels=labels)
        if cache_hit is not None:
            registry.increment("cache_requests_total", labels={"route": route_name, "hit": cache_hit})
    except Exception:
        return
