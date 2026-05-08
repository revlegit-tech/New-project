from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from .middleware import attach_request_metadata, direct_client_ip_from_handler
from .security.mutation import MutationSecurityError


class ApiError(Exception):
    """Safe API error surfaced to clients without leaking internals."""

    def __init__(self, status: int | HTTPStatus, message: str, *, code: str = "api_error") -> None:
        super().__init__(message)
        self.status = int(status)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class RequestContext:
    method: str
    path: str
    query: dict[str, list[str]]
    body: dict[str, Any]
    handler: BaseHTTPRequestHandler
    request_id: str = ""
    client_ip: str = "unknown"
    route_name: str = "unmatched"
    started_at: float = 0.0

    @classmethod
    def from_handler(cls, handler: BaseHTTPRequestHandler, *, parse_body: bool = False) -> "RequestContext":
        parsed = urlparse(handler.path)
        inbound_request_id = handler.headers.get("X-Request-Id") if hasattr(handler, "headers") else None
        request_id, client_ip, started_at = attach_request_metadata(
            handler,
            request_id=inbound_request_id,
            client_ip=direct_client_ip_from_handler(handler),
        )
        return cls(
            method=handler.command.upper(),
            path=parsed.path,
            query=parse_qs(parsed.query),
            body=read_json_body(handler) if parse_body else {},
            handler=handler,
            request_id=request_id,
            client_ip=client_ip,
            started_at=started_at,
        )


def json_response(
    handler: BaseHTTPRequestHandler,
    payload: Any,
    status: int | HTTPStatus = 200,
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(int(status))
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    request_id = getattr(handler, "request_id", None)
    if request_id:
        handler.send_header("X-Request-Id", str(request_id))
    if extra_headers:
        for key, value in extra_headers.items():
            if value is not None:
                handler.send_header(str(key), str(value))
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
        return


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as error:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header", code="bad_content_length") from error
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON", code="bad_json") from error
    if not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object", code="bad_json_shape")
    return payload


def error_payload(error: Exception) -> tuple[dict[str, Any], int]:
    if isinstance(error, ApiError):
        return {"status": "error", "code": error.code, "error": error.message}, error.status
    if isinstance(error, MutationSecurityError):
        return {"status": "error", "code": error.code, "error": error.message}, error.status
    return {
        "status": "error",
        "code": "internal_server_error",
        "error": "Internal server error",
    }, int(HTTPStatus.INTERNAL_SERVER_ERROR)
