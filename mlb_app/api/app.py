from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from mlb_app.api.middleware import ReadRateLimitMiddleware, RequestMetadataMiddleware, SecurityHeadersMiddleware
from mlb_app.api.routes import admin, data_health, edge_board, health, model_cards, observability, picks, playerboard, predictions, prop_detail, research_report, status, workflow
from mlb_app.container import AppContainer, build_container
from mlb_app.api.route_ownership import NATIVE_OWNED_ROUTES
from mlb_app.http import ApiError, error_payload
from mlb_app.security.mutation import MutationSecurityError
from mlb_app.security.trusted_proxy import effective_client_ip_from_request

logger = logging.getLogger(__name__)

LegacyDispatch = Callable[..., tuple[int, list[tuple[str, str]], bytes]]
StaticHandler = Callable[[str, str], tuple[int, list[tuple[str, str]], bytes]]


def create_app(
    *,
    container: AppContainer | None = None,
    legacy_dispatch: LegacyDispatch | None = None,
    static_handler: StaticHandler | None = None,
    csp_report_only: bool | None = None,
    csp_allow_inline: bool | None = None,
) -> FastAPI:
    """Create the native FastAPI application for Sprint 4.

    High-traffic product endpoints are registered as first-class FastAPI routes.
    A legacy catch-all remains after those routers so lower-priority routes can
    continue working until they are migrated or retired.
    """

    app = FastAPI(title="MLB App Native API", version="1.0.0")
    app.state.container = container or build_container()
    app.state.legacy_dispatch = legacy_dispatch
    app.state.static_handler = static_handler

    active_settings = app.state.container.settings
    app.add_middleware(
        SecurityHeadersMiddleware,
        csp_report_only=active_settings.csp_report_only if csp_report_only is None else csp_report_only,
        csp_allow_inline=active_settings.csp_allow_inline if csp_allow_inline is None else csp_allow_inline,
    )
    app.add_middleware(ReadRateLimitMiddleware)
    app.add_middleware(RequestMetadataMiddleware)

    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(MutationSecurityError, _mutation_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)

    app.include_router(health.router)
    app.include_router(status.router)
    app.include_router(admin.router)
    app.include_router(data_health.router)
    app.include_router(workflow.router)
    app.include_router(edge_board.router)
    app.include_router(research_report.router)
    app.include_router(playerboard.router)
    app.include_router(prop_detail.router)
    app.include_router(model_cards.router)
    app.include_router(predictions.router)
    app.include_router(observability.router)
    app.include_router(picks.router)

    if legacy_dispatch is not None:
        _install_legacy_api_gateway(app, legacy_dispatch)
    if static_handler is not None:
        _install_static_gateway(app, static_handler)
    return app


def _install_legacy_api_gateway(app: FastAPI, legacy_dispatch: LegacyDispatch) -> None:
    @app.api_route("/api/{api_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], name="legacy_api_gateway")
    async def legacy_api_gateway(api_path: str, request: Request) -> Response:
        path = f"/api/{api_path}"
        headers = _headers_from_request(request)
        body_bytes = await request.body()
        request_id = str(getattr(request.state, "request_id", "") or headers.get("X-Request-Id") or "")
        method = request.method.upper()
        if (method, path) in NATIVE_OWNED_ROUTES:
            logger.error(
                "native_owned_route_reached_legacy_gateway",
                extra={"route": path, "method": method, "request_id": request_id},
            )
            return JSONResponse(
                {"status": "error", "code": "route_owner_violation", "message": "Route is FastAPI-owned and cannot be served by legacy fallback.", "requestId": request_id},
                status_code=int(HTTPStatus.INTERNAL_SERVER_ERROR),
            )
        logger.warning(
            "legacy_api_gateway_used",
            extra={"route": path, "method": method, "request_id": request_id},
        )
        limiter = app.state.container.blocking_work_limiter
        status, response_headers, response_body = await limiter.run(
            legacy_dispatch,
            method=method,
            path=path,
            query_string=request.url.query,
            headers=headers,
            body_bytes=body_bytes,
            request_id=request_id,
            client_ip=_client_ip(request),
            route_name="legacy_api_gateway",
        )
        response_header_dict = {key: value for key, value in response_headers if key.lower() != "content-length"}
        media_type = response_header_dict.pop("Content-Type", "application/json; charset=utf-8")
        return Response(content=response_body, status_code=status, media_type=media_type, headers=response_header_dict)


def _install_static_gateway(app: FastAPI, static_handler: StaticHandler) -> None:
    @app.api_route("/{static_path:path}", methods=["GET", "HEAD"], name="static_gateway")
    async def static_gateway(static_path: str, request: Request) -> Response:
        path = "/" if not static_path else f"/{static_path}"
        request_id = str(getattr(request.state, "request_id", "") or request.headers.get("x-request-id") or "")
        limiter = app.state.container.blocking_work_limiter
        status, response_headers, response_body = await limiter.run(
            static_handler,
            path,
            request_id,
            route_name="static_gateway",
        )
        response_header_dict = {key: value for key, value in response_headers if key.lower() != "content-length"}
        media_type = response_header_dict.pop("Content-Type", "application/octet-stream")
        return Response(
            content=b"" if request.method.upper() == "HEAD" else response_body,
            status_code=status,
            media_type=media_type,
            headers=response_header_dict,
        )


async def _api_error_handler(request: Request, error: ApiError) -> JSONResponse:
    payload, status_code = error_payload(error)
    _standardize_error_payload(payload, request)
    return JSONResponse(payload, status_code=status_code)


async def _mutation_error_handler(request: Request, error: MutationSecurityError) -> JSONResponse:
    payload, status_code = error_payload(error)
    _standardize_error_payload(payload, request)
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
    return JSONResponse(payload, status_code=status_code, headers=headers)


async def _unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    payload, status_code = error_payload(error)
    _standardize_error_payload(payload, request)
    logger.exception(
        "unhandled_native_api_error",
        extra={"request_id": payload.get("requestId"), "path": request.url.path, "method": request.method},
    )
    return JSONResponse(payload, status_code=status_code)


def _standardize_error_payload(payload: dict[str, Any], request: Request) -> None:
    payload.setdefault("message", str(payload.get("error") or "Request failed"))
    payload.setdefault("requestId", str(getattr(request.state, "request_id", "") or request.headers.get("x-request-id") or ""))
    payload.setdefault("meta", {})


def _headers_from_request(request: Request) -> dict[str, str]:
    return {str(key).title(): str(value) for key, value in request.headers.items()}


def _client_ip(request: Request) -> str:
    existing = getattr(request.state, "effective_client_ip", None)
    if existing:
        return str(existing)
    container = getattr(request.app.state, "container", None)
    trusted_proxy_cidrs = getattr(getattr(container, "settings", None), "trusted_proxy_cidrs", None)
    return effective_client_ip_from_request(request, trusted_proxy_cidrs)
