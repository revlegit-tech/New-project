from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    data_dir = tmp_path / "data"
    return replace(settings, data_dir=data_dir, db_path=data_dir / "mlb_app_state.sqlite3", current_season=2026, db_enabled=True, database_url=f"sqlite:///{data_dir / 'mlb_app_state.sqlite3'}")


def client_for(settings: Settings) -> TestClient:
    return TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))


def test_data_source_capability_endpoint_returns_schema_version(tmp_path: Path) -> None:
    client = client_for(make_settings(tmp_path))

    response = client.get("/api/runtime/data-source-capabilities?date=today&season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "data-source-capability.v1"
    assert payload["resolvedDateMode"] == "today"
    assert payload["season"] == 2026
    assert {"sources", "featureGroups", "featureAudit", "featureStoreContract", "recommendations"} <= set(payload)


def test_collector_check_includes_compact_capability_summary(tmp_path: Path) -> None:
    client = client_for(make_settings(tmp_path))

    response = client.get("/api/runtime/collector-check?date=2026-06-24&season=2026")

    assert response.status_code == 200
    summary = response.json()["capabilitySummary"]
    assert {
        "featureStoreReady",
        "readyForBoard",
        "readyForBaselineTraining",
        "readyForProductionTraining",
        "missingCriticalFeatureGroups",
        "dataSourceCapabilityStatus",
    } <= set(summary)
    assert summary["readyForBaselineTraining"] is False
    assert summary["readyForProductionTraining"] is False
    assert summary["dataSourceCapabilityStatus"] in {"ok", "partial", "failed"}
