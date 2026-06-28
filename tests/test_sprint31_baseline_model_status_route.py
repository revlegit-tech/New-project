from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def test_baseline_model_status_route_is_read_only(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("read-only baseline status route must not train")

    monkeypatch.setattr("mlb_app.services.baseline_model_training_service.BaselineModelTrainingService.train", forbidden)
    settings = make_settings(tmp_path)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/runtime/baseline-model/status?date=2026-06-24&season=2026&market=batter_hits")
    payload = response.json()

    assert response.status_code == 200
    assert payload["schemaVersion"] == "baseline-model-status.v1"
    assert payload["market"] == "batter_hits"
    assert payload["artifactExists"] is False
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False
    assert payload["readyForProductionTraining"] is False
