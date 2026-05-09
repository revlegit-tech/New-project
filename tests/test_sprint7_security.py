from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from tools.security_preflight import csp_report_only_warnings
from tools.validate_vite_csp import main as validate_vite_csp_main


def _client(tmp_path: Path, **overrides: Any) -> TestClient:
    settings = replace(Settings.from_env(tmp_path), **overrides)
    container = AppContainer(settings=settings)
    return TestClient(create_app(container=container))


def test_production_csp_is_enforced_without_inline_allowance(tmp_path: Path) -> None:
    client = _client(tmp_path, csp_report_only=False, csp_allow_inline=False)

    response = client.get("/health/live", headers={"X-Request-Id": "csp-prod-1"})

    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert "Content-Security-Policy-Report-Only" not in response.headers
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]


def test_read_endpoint_rate_limit_returns_retry_after(tmp_path: Path) -> None:
    client = _client(tmp_path, read_rate_limit_per_minute=1, read_rate_limit_burst=1)

    first = client.get("/api/app/status", headers={"X-Request-Id": "rate-a-0001"})
    limited = client.get("/api/app/status", headers={"X-Request-Id": "rate-b-0001"})

    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    payload = limited.json()
    assert payload["code"] == "read_rate_limited"
    assert payload["requestId"] == "rate-b-0001"
    assert payload["meta"]["route"] == "/api/app/status"


def test_untrusted_forwarded_for_cannot_spoof_localhost_for_mutation(tmp_path: Path) -> None:
    client = TestClient(create_app(container=AppContainer(settings=Settings.from_env(tmp_path))), client=("203.0.113.9", 50000))

    response = client.post(
        "/api/bankroll/settings",
        headers={"X-Baseball-Prop-Action": "1", "X-Forwarded-For": "127.0.0.1"},
        json={"bankroll": 1000},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "localhost_required"


def test_access_log_records_direct_and_effective_client_ip_for_trusted_proxy(tmp_path: Path, capsys: Any) -> None:
    client = TestClient(create_app(container=AppContainer(settings=Settings.from_env(tmp_path))), client=("127.0.0.1", 50000))

    response = client.get("/api/app/status", headers={"X-Request-Id": "proxy-log1", "X-Forwarded-For": "198.51.100.44"})

    assert response.status_code == 200
    captured = capsys.readouterr().out.strip().splitlines()
    access_event = json.loads(captured[-1])
    assert access_event["client_ip"] == "198.51.100.44"
    assert access_event["directClientIp"] == "127.0.0.1"
    assert access_event["effectiveClientIp"] == "198.51.100.44"


def test_csp_report_only_env_zero_emits_enforcing_header(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("MLB_CSP_REPORT_ONLY", "0")
    monkeypatch.setenv("MLB_CSP_ALLOW_INLINE", "0")
    client = TestClient(create_app(container=AppContainer(settings=Settings.from_env(tmp_path))))

    response = client.get("/health/live", headers={"X-Request-Id": "csp-env-prod-1"})

    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert "Content-Security-Policy-Report-Only" not in response.headers
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]


def test_security_preflight_warns_on_report_only_csp_in_production() -> None:
    warnings = csp_report_only_warnings(
        {
            "PORT": "443",
            "MLB_CSP_REPORT_ONLY": "1",
            "MLB_CSP_ALLOW_INLINE": "0",
        }
    )

    assert len(warnings) == 1
    assert "MLB_CSP_REPORT_ONLY=1" in warnings[0]
    assert "PORT=443" in warnings[0]
    assert "MLB_CSP_REPORT_ONLY=0" in warnings[0]


def test_vite_built_frontend_has_no_csp_inline_script_violations() -> None:
    project_root = Path(__file__).resolve().parents[1]

    exit_code = validate_vite_csp_main(["--root", str(project_root)])

    assert exit_code == 0
