from __future__ import annotations

import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from mlb_app.asgi import _dispatch_api_sync, app as asgi_app
from mlb_app.wsgi import application as wsgi_application


def _call_wsgi(path: str, *, request_id: str = "sprint0-runtime") -> tuple[int, dict[str, str], dict]:
    captured: dict[str, object] = {}

    def start_response(status_line: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = int(status_line.split()[0])
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": BytesIO(b""),
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_X_REQUEST_ID": request_id,
    }
    body = b"".join(wsgi_application(environ, start_response))
    return int(captured["status"]), captured["headers"], json.loads(body.decode("utf-8"))


def _call_asgi_dispatch(path: str, *, request_id: str = "sprint0-runtime") -> tuple[int, dict[str, str], dict]:
    status, headers, body = _dispatch_api_sync(
        method="GET",
        path=path,
        query_string="",
        headers={"X-Request-Id": request_id},
        body_bytes=b"",
        request_id=request_id,
        client_ip="127.0.0.1",
    )
    return status, dict(headers), json.loads(body.decode("utf-8"))


def test_native_asgi_app_status_contract_shape() -> None:
    with TestClient(asgi_app) as client:
        response = client.get("/api/app/status", headers={"X-Request-Id": "sprint0-runtime"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["meta"]["schema"] == "app-status-v1"
    assert payload["meta"]["requestId"] == "sprint0-runtime"
    assert "productState" in payload
    assert "grading" in payload
    assert "playerboard" in payload


def test_legacy_dispatch_no_longer_owns_fastapi_product_routes() -> None:
    status, headers, payload = _call_asgi_dispatch("/api/app/status")

    assert status == 404
    assert headers["X-Request-Id"] == "sprint0-runtime"
    assert payload == {"status": "error", "code": "not_found", "error": "Not found"}


def test_wsgi_legacy_no_longer_owns_fastapi_product_routes() -> None:
    status, _headers, payload = _call_wsgi("/api/app/status")

    assert status == 404
    assert payload["code"] == "not_found"


def test_asgi_unmatched_api_returns_json_404() -> None:
    with TestClient(asgi_app) as client:
        response = client.get("/api/does-not-exist", headers={"X-Request-Id": "sprint0-runtime"})

    assert response.status_code == 404
    assert response.headers["X-Request-Id"] == "sprint0-runtime"
    assert response.json() == {"status": "error", "code": "not_found", "error": "Not found"}


def test_asgi_app_object_is_exposed() -> None:
    assert asgi_app is not None


@pytest.mark.skipif(not hasattr(asgi_app, "routes"), reason="FastAPI is not installed in this environment")
def test_fastapi_route_shell_exists_when_dependencies_are_installed() -> None:
    paths = {getattr(route, "path", "") for route in asgi_app.routes}
    assert "/api/app/status" in paths
    assert "/api/{api_path:path}" in paths
    assert "/{static_path:path}" in paths
