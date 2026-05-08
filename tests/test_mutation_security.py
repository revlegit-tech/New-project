from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pytest

import mlb_app.security.mutation as mutation
from mlb_app.security.mutation import TokenBucketRateLimiter, mutation_security_config
from mlb_app.wsgi import application


def call_wsgi(path: str, *, method: str = "POST", payload: dict[str, Any] | None = None, remote_addr: str = "127.0.0.1", headers: dict[str, str] | None = None) -> tuple[str, list[tuple[str, str]], dict[str, Any]]:
    captured: dict[str, Any] = {}
    def start_response(status: str, response_headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = response_headers
    body = json.dumps(payload or {}).encode("utf-8")
    environ: dict[str, Any] = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "", "REMOTE_ADDR": remote_addr, "wsgi.input": BytesIO(body), "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/json"}
    for key, value in (headers or {}).items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    chunks = list(application(environ, start_response))
    return captured["status"], captured["headers"], json.loads(b"".join(chunks).decode("utf-8"))


def header_value(headers: list[tuple[str, str]], name: str) -> str | None:
    for key, value in headers:
        if key.lower() == name.lower():
            return value
    return None


@pytest.fixture(autouse=True)
def reset_mutation_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    mutation.mutation_rate_limiter = TokenBucketRateLimiter()
    for key in ["MLB_ENV", "MLB_APP_ENV", "APP_ENV", "MLB_DEV_MODE", "MLB_MUTATION_TOKEN", "MLB_API_TOKEN", "MLB_ADMIN_TOKEN", "MLB_CSRF_TOKEN", "MLB_REQUIRE_CSRF", "MLB_MUTATION_RATE_LIMIT", "MLB_MUTATION_RATE_WINDOW_SECONDS"]:
        monkeypatch.delenv(key, raising=False)


def test_mutating_route_rejects_missing_action_header() -> None:
    status, _headers, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1200})
    assert status.startswith("403 ")
    assert payload["code"] == "action_header_required"


def test_local_mutation_requires_loopback_client() -> None:
    status, _headers, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1200}, remote_addr="203.0.113.9", headers={"X-Baseball-Prop-Action": "1"})
    assert status.startswith("403 ")
    assert payload["code"] == "localhost_required"


def test_local_loopback_action_header_allows_mutation() -> None:
    status, headers, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1500, "defaultUnitSize": 15, "maxUnitsPerBet": 0.25}, headers={"X-Baseball-Prop-Action": "1"})
    assert status.startswith("200 ")
    assert payload["status"] == "ok"
    assert payload["settings"]["bankroll"] == 1500
    assert header_value(headers, "X-Request-Id")


def test_staging_mutation_requires_configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_ENV", "staging")
    status, _headers, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1200}, headers={"X-Baseball-Prop-Action": "1"})
    assert status.startswith("503 ")
    assert payload["code"] == "mutation_token_not_configured"


def test_staging_mutation_accepts_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_ENV", "staging")
    monkeypatch.setenv("MLB_MUTATION_TOKEN", "test-token")
    status, _headers, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1750}, headers={"X-Baseball-Prop-Action": "1", "X-MLB-App-Token": "test-token"})
    assert status.startswith("200 ")
    assert payload["settings"]["bankroll"] == 1750


def test_production_csrf_can_be_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_ENV", "production")
    monkeypatch.setenv("MLB_MUTATION_TOKEN", "test-token")
    monkeypatch.setenv("MLB_CSRF_TOKEN", "csrf-token")
    status, _headers, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1200}, headers={"X-Baseball-Prop-Action": "1", "Authorization": "Bearer test-token"})
    assert status.startswith("403 ")
    assert payload["code"] == "csrf_token_required"
    status, _headers, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1200}, headers={"X-Baseball-Prop-Action": "1", "Authorization": "Bearer test-token", "X-CSRF-Token": "csrf-token"})
    assert status.startswith("200 ")


def test_mutation_rate_limit_returns_429_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_MUTATION_RATE_LIMIT", "2")
    monkeypatch.setenv("MLB_MUTATION_RATE_WINDOW_SECONDS", "60")
    headers = {"X-Baseball-Prop-Action": "1"}
    assert call_wsgi("/api/bankroll/settings", payload={"bankroll": 1001}, headers=headers)[0].startswith("200 ")
    assert call_wsgi("/api/bankroll/settings", payload={"bankroll": 1002}, headers=headers)[0].startswith("200 ")
    status, headers_out, payload = call_wsgi("/api/bankroll/settings", payload={"bankroll": 1003}, headers=headers)
    assert status.startswith("429 ")
    assert payload["code"] == "rate_limited"
    assert header_value(headers_out, "Retry-After") is not None


def test_config_defaults_to_local_safety_when_unconfigured() -> None:
    config = mutation_security_config({})
    assert config.runtime_mode == "local"
    assert config.localhost_required is True
    assert config.token_required is False
