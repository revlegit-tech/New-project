from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from mlb_app.api.middleware import RequestMetadataMiddleware, SecurityHeadersMiddleware
from mlb_app.api.routes import edge_board, health, model_cards, observability, picks, playerboard, predictions, prop_detail, status
from mlb_app.container import AppContainer, build_container
from mlb_app.http import ApiError, error_payload
from mlb_app.security.mutation import MutationSecurityError

LegacyDispatch = Callable[..., tuple[int, list[tuple[str, str]], bytes]]
StaticHandler = Callable[[str, str], tuple[int, list[tuple[str, str]], bytes]]


def create_app(
    *,
    container: AppContainer | None = None,
    legacy_dispatch: LegacyDispatch | None = None,
    static_handler: StaticHandler | None = None,
    csp_report_only: bool = True,
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

    app.add_middleware(SecurityHeadersMiddleware, csp_report_only=csp_report_only)
    app.add_middleware(RequestMetadataMiddleware)

    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(MutationSecurityError, _mutation_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)

    app.include_router(health.router)
    app.include_router(status.router)
    app.include_router(edge_board.router)
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
        status, response_headers, response_body = await asyncio.to_thread(
            legacy_dispatch,
            method=request.method.upper(),
            path=path,
            query_string=request.url.query,
            headers=headers,
            body_bytes=body_bytes,
            request_id=request_id,
            client_ip=_client_ip(request),
        )
        response_header_dict = {key: value for key, value in response_headers if key.lower() != "content-length"}
        media_type = response_header_dict.pop("Content-Type", "application/json; charset=utf-8")
        return Response(content=response_body, status_code=status, media_type=media_type, headers=response_header_dict)


def _install_static_gateway(app: FastAPI, static_handler: StaticHandler) -> None:
    @app.api_route("/{static_path:path}", methods=["GET", "HEAD"], name="static_gateway")
    async def static_gateway(static_path: str, request: Request) -> Response:
        path = "/" if not static_path else f"/{static_path}"
        request_id = str(getattr(request.state, "request_id", "") or request.headers.get("x-request-id") or "")
        status, response_headers, response_body = await asyncio.to_thread(static_handler, path, request_id)
        response_header_dict = {key: value for key, value in response_headers if key.lower() != "content-length"}
        media_type = response_header_dict.pop("Content-Type", "application/octet-stream")
        return Response(
            content=b"" if request.method.upper() == "HEAD" else response_body,
            status_code=status,
            media_type=media_type,
            headers=response_header_dict,
        )


async def _api_error_handler(_: Request, error: ApiError) -> JSONResponse:
    payload, status_code = error_payload(error)
    return JSONResponse(payload, status_code=status_code)


async def _mutation_error_handler(_: Request, error: MutationSecurityError) -> JSONResponse:
    payload, status_code = error_payload(error)
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
    return JSONResponse(payload, status_code=status_code, headers=headers)


async def _unexpected_error_handler(_: Request, error: Exception) -> JSONResponse:
    payload, status_code = error_payload(error)
    return JSONResponse(payload, status_code=status_code)


def _headers_from_request(request: Request) -> dict[str, str]:
    return {str(key).title(): str(value) for key, value in request.headers.items()}


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
