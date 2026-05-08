from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from mlb_app.wsgi import application


def call_wsgi(path: str, method: str = "GET", body: bytes = b"") -> tuple[str, list[tuple[str, str]], bytes]:
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
    }
    chunks = list(application(environ, start_response))
    return captured["status"], captured["headers"], b"".join(chunks)


def test_wsgi_app_status_returns_json() -> None:
    status, headers, body = call_wsgi("/api/app/status")
    assert status.startswith("200 ")
    assert any(key.lower() == "content-type" and "application/json" in value for key, value in headers)
    assert any(key.lower() == "x-request-id" and value for key, value in headers)
    payload = json.loads(body.decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["productState"] == "research_mode"


def test_wsgi_unknown_api_returns_json_404() -> None:
    status, headers, body = call_wsgi("/api/not-real")
    assert status.startswith("404 ")
    assert any(key.lower() == "content-type" and "application/json" in value for key, value in headers)
    assert any(key.lower() == "x-request-id" and value for key, value in headers)
    payload = json.loads(body.decode("utf-8"))
    assert payload["code"] == "not_found"
