from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def test_calibration_and_backtest_status_routes_are_read_only(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("read-only status route must not write evaluation artifacts")

    monkeypatch.setattr("mlb_app.services.model_calibration_service.ModelCalibrationService.calibrate", forbidden)
    monkeypatch.setattr("mlb_app.services.model_backtest_service.ModelBacktestService.backtest", forbidden)
    settings = make_settings(tmp_path)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    calibration = client.get("/api/runtime/model-calibration/status?date=2026-06-24&season=2026&market=batter_hits")
    backtest = client.get("/api/runtime/model-backtest/status?date=2026-06-24&season=2026&market=batter_hits")

    assert calibration.status_code == 200
    assert backtest.status_code == 200
    calibration_payload = calibration.json()
    backtest_payload = backtest.json()
    assert calibration_payload["schemaVersion"] == "model-calibration-status.v1"
    assert calibration_payload["calibrationStatus"] == "missing"
    assert calibration_payload["modelTrainingTriggered"] is False
    assert calibration_payload["externalApiCallsMade"] is False
    assert backtest_payload["schemaVersion"] == "model-backtest-status.v1"
    assert backtest_payload["backtestStatus"] == "missing"
    assert backtest_payload["modelTrainingTriggered"] is False
    assert backtest_payload["externalApiCallsMade"] is False
