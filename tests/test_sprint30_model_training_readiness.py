from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.contracts.feature_store_schema import pregame_feature_names
from mlb_app.services.model_training_readiness_service import ModelTrainingReadinessService


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    return replace(settings, data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_feature_matrix(settings: Settings, date_label: str) -> None:
    row = {field: "" for field in pregame_feature_names()}
    row.update({"date": date_label, "season": 2026, "player": "Aaron Judge", "team": "NYY", "market": "batter_total_bases"})
    write_csv(settings.data_dir / "features" / f"prop_features_{date_label}.csv", [row], fieldnames=pregame_feature_names())


def test_label_sufficiency_and_two_class_validation_are_market_level(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_feature_matrix(settings, date_label)
    rows = [
        {"date": date_label, "market": "batter_total_bases", "hit": "1" if index % 2 else "0", "result": "win" if index % 2 else "loss"}
        for index in range(100)
    ]
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", rows)

    payload = ModelTrainingReadinessService(settings).payload(date_label=date_label, season=2026)
    market = payload["markets"][0]

    assert payload["schemaVersion"] == "model-training-readiness.v1"
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False
    assert market["market"] == "batter_total_bases"
    assert market["labelRows"] == 100
    assert market["hitRows"] == 50
    assert market["missRows"] == 50
    assert market["twoClassTarget"] is True
    assert market["baselineEligible"] is True
    assert payload["readyForBaselineTraining"] is True


def test_production_readiness_remains_false_without_calibration_and_backtest(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_feature_matrix(settings, date_label)
    rows = [
        {"date": date_label, "market": "batter_hits", "hit": "1" if index % 2 else "0", "result": "win" if index % 2 else "loss"}
        for index in range(500)
    ]
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", rows)

    payload = ModelTrainingReadinessService(settings).payload(date_label=date_label, season=2026)
    market = payload["markets"][0]

    assert payload["readyForBaselineTraining"] is True
    assert payload["readyForProductionTraining"] is False
    assert market["productionEligible"] is False
    assert any("Calibration artifacts are missing" in reason for reason in market["reasons"])
    assert any("Backtest artifacts are missing" in reason for reason in market["reasons"])


def test_one_class_or_tiny_labels_do_not_make_baseline_ready(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_feature_matrix(settings, date_label)
    rows = [{"date": date_label, "market": "pitcher_strikeouts", "hit": "1", "result": "win"} for _ in range(25)]
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", rows)

    payload = ModelTrainingReadinessService(settings).payload(date_label=date_label, season=2026)
    market = payload["markets"][0]

    assert payload["readyForBaselineTraining"] is False
    assert market["baselineEligible"] is False
    assert market["twoClassTarget"] is False
    assert any("Label rows below baseline threshold" in reason for reason in market["reasons"])
    assert any("Two-class target validation" in reason for reason in market["reasons"])


def test_model_training_readiness_route_does_not_trigger_training(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("read-only readiness route must not train")

    monkeypatch.setattr("mlb_app.services.model_training_service.ModelTrainingService.train_market", forbidden)
    settings = make_settings(tmp_path)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/runtime/model-training/readiness?date=2026-06-24&season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "model-training-readiness.v1"
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False
