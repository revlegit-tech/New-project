from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from io import BytesIO
from typing import Any, Iterable
from urllib.parse import parse_qs

from .config import settings
from .http import ApiError, RequestContext, error_payload
from .middleware import (
    AccessLogEvent,
    attach_request_metadata,
    direct_client_ip_from_environ,
    log_access,
    monotonic_ms,
)
from .server import build_router, resolve_static_target

router = build_router()
public_root = settings.public_dir.resolve()

_STATUS_PHRASES = {status.value: status.phrase for status in HTTPStatus}


class WsgiHandlerAdapter:
    """Small adapter that lets existing route handlers run under WSGI.

    Current modular routes write through mlb_app.http.json_response(), which
    expects a tiny subset of BaseHTTPRequestHandler. This adapter preserves the
    route/service contracts while adding production request metadata at the
    WSGI boundary.
    """

    def __init__(
        self,
        *,
        method: str,
        path: str,
        query_string: str,
        headers: dict[str, str],
        body_bytes: bytes,
        request_id: str,
        client_ip: str,
        started_at: float,
    ) -> None:
        self.command = method
        self.path = f"{path}?{query_string}" if query_string else path
        self.headers = headers
        self.rfile = BytesIO(body_bytes)
        self.wfile = BytesIO()
        self.status = int(HTTPStatus.OK)
        self.response_headers: list[tuple[str, str]] = []
        attach_request_metadata(self, request_id=request_id, client_ip=client_ip, started_at=started_at)

    def send_response(self, status: int) -> None:
        self.status = int(status)

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return None

    def send_error(self, status: int | HTTPStatus, message: str | None = None) -> None:
        payload = {
            "status": "error",
            "code": "not_found" if int(status) == 404 else "http_error",
            "error": message or _STATUS_PHRASES.get(int(status), "HTTP error"),
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-Id", str(self.request_id))
        self.send_header("Content-Length", str(len(body)))
        self.wfile.write(body)


def _headers_from_environ(environ: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            name = key[5:].replace("_", "-").title()
            headers[name] = str(value)
    if "CONTENT_TYPE" in environ:
        headers["Content-Type"] = str(environ["CONTENT_TYPE"])
    if "CONTENT_LENGTH" in environ:
        headers["Content-Length"] = str(environ["CONTENT_LENGTH"])
    return headers


def _read_body(environ: dict[str, Any]) -> bytes:
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header", code="bad_content_length")
    if length <= 0:
        return b""
    return environ["wsgi.input"].read(length)


def _parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON", code="bad_json") from error
    if not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object", code="bad_json_shape")
    return payload


def _status_line(status: int) -> str:
    return f"{status} {_STATUS_PHRASES.get(status, 'Unknown')}"


def _base_headers(content_type: str, body: bytes, request_id: str) -> list[tuple[str, str]]:
    return [("Content-Type", content_type), ("X-Request-Id", request_id), ("Content-Length", str(len(body)))]


def _not_found(request_id: str) -> tuple[int, list[tuple[str, str]], bytes]:
    body = json.dumps({"status": "error", "code": "not_found", "error": "Not found"}).encode("utf-8")
    return int(HTTPStatus.NOT_FOUND), _base_headers("application/json; charset=utf-8", body, request_id), body


def _serve_static(path: str, request_id: str = "test-request") -> tuple[int, list[tuple[str, str]], bytes]:
    target = resolve_static_target(public_root, path)
    if target is None:
        body = b"Forbidden"
        return int(HTTPStatus.FORBIDDEN), _base_headers("text/plain; charset=utf-8", body, request_id), body
    if not target.exists() or target.is_dir():
        body = b"Not found"
        return int(HTTPStatus.NOT_FOUND), _base_headers("text/plain; charset=utf-8", body, request_id), body

    content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if target.suffix == ".html":
        content_type = "text/html; charset=utf-8"
    elif target.suffix == ".css":
        content_type = "text/css; charset=utf-8"
    elif target.suffix == ".js":
        content_type = "application/javascript; charset=utf-8"
    body = target.read_bytes()
    return int(HTTPStatus.OK), _base_headers(content_type, body, request_id), body


def _log_wsgi_request(
    *,
    request_id: str,
    method: str,
    path: str,
    status: int,
    started_at: float,
    client_ip: str,
    route: str,
) -> None:
    log_access(
        AccessLogEvent(
            request_id=request_id,
            method=method,
            path=path,
            status=status,
            elapsed_ms=monotonic_ms(started_at),
            client_ip=client_ip,
            route=route,
        )
    )


def application(environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
    method = str(environ.get("REQUEST_METHOD", "GET")).upper()
    path = str(environ.get("PATH_INFO", "/"))
    query_string = str(environ.get("QUERY_STRING", ""))
    headers = _headers_from_environ(environ)
    request_id, client_ip, started_at = attach_request_metadata(
        object(),
        request_id=headers.get("X-Request-Id"),
        client_ip=direct_client_ip_from_environ(environ),
    )

    if path.startswith("/api/"):
        try:
            body_bytes = _read_body(environ)
            body = _parse_json_body(body_bytes) if method in {"POST", "PUT", "PATCH"} else {}
            adapter = WsgiHandlerAdapter(
                method=method,
                path=path,
                query_string=query_string,
                headers=headers,
                body_bytes=body_bytes,
                request_id=request_id,
                client_ip=client_ip,
                started_at=started_at,
            )
            context = RequestContext(
                method=method,
                path=path,
                query=parse_qs(query_string),
                body=body,
                handler=adapter,  # type: ignore[arg-type]
                request_id=request_id,
                client_ip=client_ip,
                started_at=started_at,
            )
            handled = router.dispatch(context)
        except Exception as error:  # noqa: BLE001 - final WSGI safety boundary
            payload, status = error_payload(error)
            adapter = WsgiHandlerAdapter(
                method=method,
                path=path,
                query_string=query_string,
                headers=headers,
                body_bytes=b"",
                request_id=request_id,
                client_ip=client_ip,
                started_at=started_at,
            )
            response_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            adapter.send_response(status)
            adapter.send_header("Content-Type", "application/json; charset=utf-8")
            adapter.send_header("Cache-Control", "no-store")
            adapter.send_header("X-Request-Id", request_id)
            adapter.send_header("Content-Length", str(len(response_body)))
            adapter.wfile.write(response_body)
            handled = True
            _log_wsgi_request(
                request_id=request_id,
                method=method,
                path=path,
                status=status,
                started_at=started_at,
                client_ip=client_ip,
                route="wsgi_error_boundary",
            )

        if not handled:
            status, response_headers, response_body = _not_found(request_id)
            start_response(_status_line(status), response_headers)
            _log_wsgi_request(
                request_id=request_id,
                method=method,
                path=path,
                status=status,
                started_at=started_at,
                client_ip=client_ip,
                route="unmatched_api",
            )
            return [response_body]
        response_body = adapter.wfile.getvalue()
        start_response(_status_line(adapter.status), adapter.response_headers)
        return [response_body]

    status, response_headers, response_body = _serve_static(path, request_id)
    start_response(_status_line(status), response_headers)
    _log_wsgi_request(
        request_id=request_id,
        method=method,
        path=path,
        status=status,
        started_at=started_at,
        client_ip=client_ip,
        route="static",
    )
    return [response_body]
