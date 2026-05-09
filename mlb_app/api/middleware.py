from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from mlb_app.middleware import AccessLogEvent, log_access, monotonic_ms, normalize_request_id
from mlb_app.security.trusted_proxy import direct_client_ip_from_request, effective_client_ip_from_request

READ_RATE_LIMITED_PATHS: frozenset[str] = frozenset(
    {
        "/api/app/status",
        "/api/edge-board",
        "/api/playerboard",
        "/api/playerboard/health",
        "/api/prop-detail",
        "/api/model-cards",
        "/api/model-card",
        "/api/data-health",
        "/api/data-health/dashboard",
        "/api/grading/health",
        "/api/workflows/health",
        "/api/prop-ml/status",
        "/api/observability/metrics",
    }
)


class RequestMetadataMiddleware(BaseHTTPMiddleware):
    """Attach request ids/effective client IPs to native FastAPI requests and log access records."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started_at = time.perf_counter()
        request_id = normalize_request_id(request.headers.get("x-request-id"))
        container = getattr(request.app.state, "container", None)
        trusted_proxy_cidrs = getattr(getattr(container, "settings", None), "trusted_proxy_cidrs", None)
        direct_client_ip = direct_client_ip_from_request(request)
        effective_client_ip = effective_client_ip_from_request(request, trusted_proxy_cidrs)
        request.state.request_id = request_id
        request.state.started_at = started_at
        request.state.direct_client_ip = direct_client_ip
        request.state.effective_client_ip = effective_client_ip
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
                client_ip=effective_client_ip,
                route=route_name,
                cache_hit=cache_hit,
                rate_limited=response.status_code == int(HTTPStatus.TOO_MANY_REQUESTS),
                direct_client_ip=direct_client_ip,
                effective_client_ip=effective_client_ip,
            )
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline browser hardening headers to API and static responses."""

    def __init__(self, app: Any, *, csp_report_only: bool = False, csp_allow_inline: bool = False) -> None:
        super().__init__(app)
        self.csp_report_only = csp_report_only
        self.csp_allow_inline = csp_allow_inline

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        script_src = "script-src 'self'" + (" 'unsafe-inline'" if self.csp_allow_inline else "")
        style_src = "style-src 'self'" + (" 'unsafe-inline'" if self.csp_allow_inline else "")
        csp_value = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            f"{script_src}; "
            f"{style_src}"
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


class ReadRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit expensive read/admin endpoints using AppContainer configuration."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        container = getattr(request.app.state, "container", None)
        settings = getattr(container, "settings", None)
        limiter = getattr(container, "read_rate_limiter", None)
        if container is None or settings is None or limiter is None or not _should_rate_limit(request):
            return await call_next(request)

        trusted_proxy_cidrs = getattr(settings, "trusted_proxy_cidrs", None)
        direct_client_ip = direct_client_ip_from_request(request)
        effective_client_ip = effective_client_ip_from_request(request, trusted_proxy_cidrs)
        request.state.direct_client_ip = direct_client_ip
        request.state.effective_client_ip = effective_client_ip
        route_key = _rate_limit_route_key(request)
        is_admin = request.url.path.startswith("/api/admin/")
        per_minute = int(settings.admin_rate_limit_per_minute if is_admin else settings.read_rate_limit_per_minute)
        burst = int(settings.admin_rate_limit_per_minute if is_admin else settings.read_rate_limit_burst)
        decision = limiter.allow(
            f"{effective_client_ip}:{request.method.upper()}:{route_key}",
            capacity=max(1, burst),
            window_seconds=60.0,
            refill_per_second=max(1, per_minute) / 60.0,
        )
        _record_rate_limit_metrics(container, request, route_key, decision.allowed)
        if decision.allowed:
            response = await call_next(request)
            response.headers.setdefault("X-RateLimit-Limit", str(per_minute))
            response.headers.setdefault("X-RateLimit-Remaining", str(decision.remaining))
            return response

        request_id = str(getattr(request.state, "request_id", "") or request.headers.get("x-request-id") or normalize_request_id(None))
        payload = {
            "status": "error",
            "code": "read_rate_limited",
            "message": "Read endpoint rate limit exceeded.",
            "requestId": request_id,
            "meta": {"route": route_key, "limitPerMinute": per_minute, "burst": burst},
        }
        return JSONResponse(
            payload,
            status_code=int(HTTPStatus.TOO_MANY_REQUESTS),
            headers={"Retry-After": str(decision.retry_after), "X-Request-Id": request_id, "X-RateLimit-Limit": str(per_minute), "X-RateLimit-Remaining": "0"},
        )


def _should_rate_limit(request: Request) -> bool:
    path = request.url.path
    method = request.method.upper()
    if path.startswith("/api/admin/"):
        return method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    if method != "GET":
        return False
    return path in READ_RATE_LIMITED_PATHS or path.startswith("/api/model-cards/")


def _rate_limit_route_key(request: Request) -> str:
    route = request.scope.get("route")
    path = str(getattr(route, "path", "") or request.url.path)
    return path


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


def _record_rate_limit_metrics(container: Any, request: Request, route_key: str, allowed: bool) -> None:
    try:
        registry = getattr(container, "metrics", None)
        if registry is not None:
            registry.increment(
                "rate_limit_checks_total",
                labels={"route": route_key, "method": request.method.upper(), "allowed": allowed},
            )
            if not allowed:
                registry.increment("rate_limit_rejections_total", labels={"route": route_key, "method": request.method.upper()})
    except Exception:
        return
