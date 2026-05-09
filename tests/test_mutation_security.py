from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import mlb_app.security.mutation as mutation
from mlb_app.asgi import app as asgi_app
from mlb_app.security.mutation import TokenBucketRateLimiter, mutation_security_config


def call_asgi(
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    remote_addr: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    with TestClient(asgi_app, client=(remote_addr, 50000)) as client:
        response = client.post(path, json=payload or {}, headers=headers or {})
    return response.status_code, dict(response.headers), response.json()


def header_value(headers: dict[str, str], name: str) -> str | None:
    return headers.get(name) or headers.get(name.lower())


@pytest.fixture(autouse=True)
def reset_mutation_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    mutation.mutation_rate_limiter = TokenBucketRateLimiter()
    for key in ["MLB_ENV", "MLB_APP_ENV", "APP_ENV", "MLB_DEV_MODE", "MLB_MUTATION_TOKEN", "MLB_API_TOKEN", "MLB_ADMIN_TOKEN", "MLB_CSRF_TOKEN", "MLB_REQUIRE_CSRF", "MLB_MUTATION_RATE_LIMIT", "MLB_MUTATION_RATE_WINDOW_SECONDS"]:
        monkeypatch.delenv(key, raising=False)


def test_mutating_route_rejects_missing_action_header() -> None:
    status, _headers, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1200})
    assert status == 403
    assert payload["code"] == "action_header_required"


def test_local_mutation_requires_loopback_client() -> None:
    status, _headers, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1200}, remote_addr="203.0.113.9", headers={"X-Baseball-Prop-Action": "1"})
    assert status == 403
    assert payload["code"] == "localhost_required"


def test_local_loopback_action_header_allows_mutation() -> None:
    status, headers, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1500, "defaultUnitSize": 15, "maxUnitsPerBet": 0.25}, headers={"X-Baseball-Prop-Action": "1"})
    assert status == 200
    assert payload["status"] == "ok"
    assert payload["settings"]["bankroll"] == 1500
    assert header_value(headers, "X-Request-Id")


def test_staging_mutation_requires_configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_ENV", "staging")
    status, _headers, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1200}, headers={"X-Baseball-Prop-Action": "1"})
    assert status == 503
    assert payload["code"] == "mutation_token_not_configured"


def test_staging_mutation_accepts_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_ENV", "staging")
    monkeypatch.setenv("MLB_MUTATION_TOKEN", "test-token")
    status, _headers, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1750}, headers={"X-Baseball-Prop-Action": "1", "X-MLB-App-Token": "test-token"})
    assert status == 200
    assert payload["settings"]["bankroll"] == 1750


def test_production_csrf_can_be_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_ENV", "production")
    monkeypatch.setenv("MLB_MUTATION_TOKEN", "test-token")
    monkeypatch.setenv("MLB_CSRF_TOKEN", "csrf-token")
    status, _headers, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1200}, headers={"X-Baseball-Prop-Action": "1", "Authorization": "Bearer test-token"})
    assert status == 403
    assert payload["code"] == "csrf_token_required"
    status, _headers, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1200}, headers={"X-Baseball-Prop-Action": "1", "Authorization": "Bearer test-token", "X-CSRF-Token": "csrf-token"})
    assert status == 200


def test_mutation_rate_limit_returns_429_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_MUTATION_RATE_LIMIT", "2")
    monkeypatch.setenv("MLB_MUTATION_RATE_WINDOW_SECONDS", "60")
    headers = {"X-Baseball-Prop-Action": "1"}
    assert call_asgi("/api/bankroll/settings", payload={"bankroll": 1001}, headers=headers)[0] == 200
    assert call_asgi("/api/bankroll/settings", payload={"bankroll": 1002}, headers=headers)[0] == 200
    status, headers_out, payload = call_asgi("/api/bankroll/settings", payload={"bankroll": 1003}, headers=headers)
    assert status == 429
    assert payload["code"] == "rate_limited"
    assert header_value(headers_out, "Retry-After") is not None


def test_config_defaults_to_local_safety_when_unconfigured() -> None:
    config = mutation_security_config({})
    assert config.runtime_mode == "local"
    assert config.localhost_required is True
    assert config.token_required is False
