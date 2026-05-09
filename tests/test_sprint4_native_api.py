from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def _app(tmp_path: Path) -> TestClient:
    settings = Settings.from_env(tmp_path)
    container = AppContainer(settings=settings)

    def legacy_dispatch(**_: Any) -> tuple[int, list[tuple[str, str]], bytes]:
        body = json.dumps({"status": "ok", "route": "legacy"}).encode("utf-8")
        return 209, [("Content-Type", "application/json; charset=utf-8"), ("X-Request-Id", "native-test")], body

    def static_handler(path: str, request_id: str) -> tuple[int, list[tuple[str, str]], bytes]:
        return 200, [("Content-Type", "text/plain; charset=utf-8"), ("X-Request-Id", request_id)], path.encode("utf-8")

    return TestClient(create_app(container=container, legacy_dispatch=legacy_dispatch, static_handler=static_handler))


def test_native_health_and_security_headers(tmp_path: Path) -> None:
    client = _app(tmp_path)

    response = client.get("/health/live", headers={"X-Request-Id": "native-health"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ok": True, "checks": {"process": "alive"}}
    assert response.headers["X-Request-Id"] == "native-health"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert "Content-Security-Policy-Report-Only" not in response.headers


def test_native_route_precedes_legacy_gateway(tmp_path: Path) -> None:
    client = _app(tmp_path)

    native = client.get("/api/app/status", headers={"X-Request-Id": "native-status"})
    fallback = client.get("/api/not-yet-migrated", headers={"X-Request-Id": "legacy-route"})

    assert native.status_code == 200
    assert native.json()["status"] == "ok"
    assert native.json()["meta"]["requestId"] == "native-status"
    assert native.status_code != 209
    assert fallback.status_code == 209
    assert fallback.json()["route"] == "legacy"


def test_native_pick_and_bankroll_routes_use_sqlite_container(tmp_path: Path) -> None:
    client = _app(tmp_path)
    mutation_headers = {
        "X-Request-Id": "native-picks",
        "X-Baseball-Prop-Action": "1",
        "X-Forwarded-For": "127.0.0.1",
    }

    bankroll = client.post(
        "/api/bankroll/settings",
        headers=mutation_headers,
        json={"bankroll": 1000, "defaultUnitSize": 10, "maxUnitsPerBet": 0.25},
    )
    created = client.post(
        "/api/my-picks",
        headers=mutation_headers,
        json={
            "date": "2026-05-07",
            "player": "Aaron Judge",
            "team": "NYY",
            "opponent": "BAL",
            "market": "batter_hits",
            "line": "0.5",
            "americanOdds": "-110",
            "decisionLabel": "Watchlist",
            "readinessLabel": "Research only",
            "stakeUnits": 1,
        },
    )
    listed = client.get("/api/my-picks")

    assert bankroll.status_code == 200
    assert bankroll.json()["settings"]["bankroll"] == 1000
    assert created.status_code == 200
    assert created.json()["pick"]["stakeUnits"] == 0.0
    assert listed.status_code == 200
    assert listed.json()["pickCount"] == 1
    assert listed.json()["storage"]["sourceOfTruth"] == "sqlite"
