from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.asgi import app as asgi_app


def _client() -> TestClient:
    return TestClient(asgi_app, client=("203.0.113.9", 50000))


def test_api_response_has_request_id_header() -> None:
    with _client() as client:
        response = client.get("/api/app/status")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    request_id = response.headers.get("X-Request-Id")
    assert request_id is not None
    assert len(request_id) >= 8


def test_inbound_safe_request_id_is_preserved_for_correlation() -> None:
    with _client() as client:
        response = client.get("/api/app/status", headers={"X-Request-Id": "req-test-1234"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "req-test-1234"


def test_bad_inbound_request_id_is_replaced() -> None:
    with _client() as client:
        response = client.get("/api/app/status", headers={"X-Request-Id": "bad\nheader"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") != "bad\nheader"


def test_unknown_api_response_has_request_id_header() -> None:
    with _client() as client:
        response = client.get("/api/not-real")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert response.headers.get("X-Request-Id") is not None


def test_static_response_has_request_id_header() -> None:
    with _client() as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.content
    assert response.headers.get("X-Request-Id") is not None


def test_structured_access_log_contains_request_id(capsys: Any) -> None:
    with _client() as client:
        response = client.get("/api/app/status", headers={"X-Request-Id": "req-log-1234"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "req-log-1234"

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured
    access_event = json.loads(captured[-1])
    assert access_event["event"] == "http_request"
    assert access_event["requestId"] == "req-log-1234"
    assert access_event["method"] == "GET"
    assert access_event["path"] == "/api/app/status"
    assert access_event["status"] == 200
    assert access_event["client_ip"] == "203.0.113.9"
    assert access_event["route"] == "native_app_status"
