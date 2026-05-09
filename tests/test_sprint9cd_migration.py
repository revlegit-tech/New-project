from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.server import build_router


def _client(tmp_path: Path) -> tuple[TestClient, AppContainer]:
    settings = Settings.from_env(tmp_path)
    container = AppContainer(settings=settings)
    return TestClient(create_app(container=container)), container


def test_sprint9c_routes_are_native_and_container_backed(tmp_path: Path) -> None:
    client, container = _client(tmp_path)
    dashboard_id = id(container.data_health_dashboard_service)

    assert build_router()._routes == {}

    paths = [
        "/api/data-health?date=2026-05-07",
        "/api/data-health/dashboard?season=2026&date=2026-05-07",
        "/api/grading/health?date=2026-05-07",
        "/api/workflows/health",
        "/api/prop-ml/status",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "schemaVersion" in response.json(), path

    assert id(container.data_health_dashboard_service) == dashboard_id


def test_sprint9d_domain_metrics_and_status_surface(tmp_path: Path) -> None:
    client, container = _client(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    container.playerboard_repository.write_snapshot_rows(
        season=container.settings.current_season,
        replace=True,
        rows=[
            {
                "snapshotAt": now,
                "date": "2026-05-07",
                "player": "Metric Batter",
                "team": "NYY",
                "opponent": "BOS",
                "market": "batter_hits",
                "marketDisplay": "Batter Hits",
                "line": "0.5",
                "americanOdds": "-110",
                "finalProbabilityPercent": "58.0",
                "impliedProbabilityPercent": "52.0",
                "finalEdgePercent": "6.0",
                "confidence": "Medium",
            }
        ],
    )

    health = client.get(f"/api/playerboard/health?season={container.settings.current_season}&date=2026-05-07")
    assert health.status_code == 200

    status = client.get(f"/api/app/status?season={container.settings.current_season}")
    assert status.status_code == 200
    status_payload: dict[str, Any] = status.json()
    assert "snapshotAgeSeconds" in status_payload
    assert "boardCacheStatus" in status_payload

    metrics = client.get("/api/observability/metrics")
    assert metrics.status_code == 200
    payload = metrics.json()
    names = {series["name"] for group in ("counters", "histograms", "gauges") for series in payload[group]}
    assert "board_snapshot_age_seconds" in names
    assert "board_build_duration_ms" in names
    assert "board_snapshot_rows" in names
    assert "board_cache_misses_total" in names
    assert "board_cache_entries" in names
