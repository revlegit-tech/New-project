from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    return replace(settings, current_season=2026, db_enabled=True, database_url=f"sqlite:///{settings.state_db_path}")


def client_for(settings: Settings) -> TestClient:
    return TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))


def test_collector_check_route_returns_schema_version(tmp_path: Path) -> None:
    client = client_for(make_settings(tmp_path))

    response = client.get("/api/runtime/collector-check?date=2026-06-24&season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "collector-check.v1"
    assert payload["date"] == "2026-06-24"
    assert payload["season"] == 2026
    assert {"checks", "counts", "files", "runtime", "recommendations"} <= set(payload)


def test_collector_check_accepts_today_date_alias(tmp_path: Path) -> None:
    client = client_for(make_settings(tmp_path))

    response = client.get("/api/runtime/collector-check?date=today")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "collector-check.v1"
    assert payload["resolvedDateMode"] == "today"
    assert len(payload["date"]) == 10


def test_collector_check_endpoint_does_not_build_playerboard(tmp_path: Path, monkeypatch) -> None:
    def explode_build_playerboard(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("collector check must not call build_playerboard")

    monkeypatch.setattr("mlb_app.services.playerboard_service.build_playerboard", explode_build_playerboard)
    client = client_for(make_settings(tmp_path))

    response = client.get("/api/runtime/collector-check?date=2026-06-24&season=2026")

    assert response.status_code == 200
    assert response.json()["schemaVersion"] == "collector-check.v1"
