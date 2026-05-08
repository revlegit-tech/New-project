from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from mlb_app.wsgi import application


def call_wsgi(
    path: str,
    *,
    method: str = "GET",
    body: bytes = b"",
    request_id: str | None = None,
) -> tuple[str, list[tuple[str, str]], bytes]:
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "wsgi.input": BytesIO(body),
        "CONTENT_LENGTH": str(len(body)),
        "REMOTE_ADDR": "203.0.113.9",
    }
    if request_id is not None:
        environ["HTTP_X_REQUEST_ID"] = request_id
    chunks = list(application(environ, start_response))
    return captured["status"], captured["headers"], b"".join(chunks)


def header_value(headers: list[tuple[str, str]], name: str) -> str | None:
    for key, value in headers:
        if key.lower() == name.lower():
            return value
    return None


def test_api_response_has_request_id_header() -> None:
    status, headers, body = call_wsgi("/api/app/status")
    assert status.startswith("200 ")
    assert json.loads(body.decode("utf-8"))["status"] == "ok"
    request_id = header_value(headers, "X-Request-Id")
    assert request_id is not None
    assert len(request_id) >= 8


def test_inbound_safe_request_id_is_preserved_for_correlation() -> None:
    status, headers, _body = call_wsgi("/api/app/status", request_id="req-test-1234")
    assert status.startswith("200 ")
    assert header_value(headers, "X-Request-Id") == "req-test-1234"


def test_bad_inbound_request_id_is_replaced() -> None:
    status, headers, _body = call_wsgi("/api/app/status", request_id="bad\nheader")
    assert status.startswith("200 ")
    assert header_value(headers, "X-Request-Id") != "bad\nheader"


def test_unknown_api_response_has_request_id_header() -> None:
    status, headers, body = call_wsgi("/api/not-real")
    assert status.startswith("404 ")
    assert json.loads(body.decode("utf-8"))["code"] == "not_found"
    assert header_value(headers, "X-Request-Id") is not None


def test_static_response_has_request_id_header() -> None:
    status, headers, body = call_wsgi("/")
    assert status.startswith("200 ")
    assert body
    assert header_value(headers, "X-Request-Id") is not None


def test_structured_access_log_contains_request_id(capsys: Any) -> None:
    status, headers, _body = call_wsgi("/api/app/status", request_id="req-log-1234")
    assert status.startswith("200 ")
    assert header_value(headers, "X-Request-Id") == "req-log-1234"

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured
    access_event = json.loads(captured[-1])
    assert access_event["event"] == "http_request"
    assert access_event["requestId"] == "req-log-1234"
    assert access_event["method"] == "GET"
    assert access_event["path"] == "/api/app/status"
    assert access_event["status"] == 200
    assert access_event["client_ip"] == "203.0.113.9"
    assert access_event["route"] == "GET /api/app/status"
