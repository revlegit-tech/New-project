from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    data_dir = tmp_path / "data"
    return replace(
        settings,
        data_dir=data_dir,
        db_path=data_dir / "mlb_app_state.sqlite3",
        current_season=2026,
        db_enabled=True,
        database_url=f"sqlite:///{data_dir / 'mlb_app_state.sqlite3'}",
    )


class FakeCollector:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def payload(self, *, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        return {
            "schemaVersion": "collector-check.v1",
            "status": "partial",
            "date": date_label,
            "season": season,
            "counts": {
                "activePlayerboardRows": 12,
                "propsRows": 7,
                "oddsSnapshots": 1,
                "normalizedOddsFiles": 0,
                "gameMarketRows": 0,
                "umpireRows": 0,
            },
            "recommendations": ["Optional provider is missing; board fallback remains available."],
        }


class FakeFeatureStore:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def status(self, *, date_label: str | None = None, season: int | None = None, materialize: bool = False) -> dict[str, Any]:
        assert materialize is False
        return {"schemaVersion": "feature-store-materializer.v1", "rows": 0, "warnings": ["Feature store is partial."]}


class FakeReadiness:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def payload(self, *, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        return {
            "schemaVersion": "model-training-readiness.v1",
            "status": "warning",
            "readyForProductionTraining": False,
            "eligibleProductionMarkets": [],
            "markets": [{"market": "batter_hits", "status": "research_only"}],
            "warnings": ["Production model gates are incomplete."],
        }


def test_daily_health_warns_but_serves_when_board_available(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mlb_app.services.daily_health_service.CollectorVerificationService", FakeCollector)
    monkeypatch.setattr("mlb_app.services.daily_health_service.FeatureStoreMaterializer", FakeFeatureStore)
    monkeypatch.setattr("mlb_app.services.daily_health_service.ModelTrainingReadinessService", FakeReadiness)
    settings = make_settings(tmp_path)
    (settings.data_dir / "status").mkdir(parents=True)
    (settings.data_dir / "status" / "daily_workflow_status.json").write_text('{"status": "failed"}\n', encoding="utf-8")

    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))
    response = client.get("/api/runtime/daily-health?date=2026-06-24&season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "daily-health.v1"
    assert payload["overallStatus"] == "warning"
    assert payload["servingSafe"] is True
    assert payload["boardAvailable"] is True
    assert payload["scheduledCollectorStatus"] == "failed"
    assert payload["weeklyRepairStatus"] == "unknown"
    assert payload["productionTrainingReady"] is False
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False
    assert {stage["name"] for stage in payload["stages"]} >= {"playerboard build", "model readiness", "weekly repair"}
