from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.contracts.feature_store_schema import postgame_label_names, pregame_feature_names
from mlb_app.services.feature_store_materializer import FeatureStoreMaterializer


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    data_dir = tmp_path / "data"
    return replace(settings, data_dir=data_dir, db_path=data_dir / "mlb_app_state.sqlite3", current_season=2026, db_enabled=True, database_url=f"sqlite:///{data_dir / 'mlb_app_state.sqlite3'}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_feature_matrix_materializer_excludes_postgame_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_csv(
        settings.data_dir / "odds" / f"propline_props_{date_label}.csv",
        [
            {
                "date": date_label,
                "market": "batter_total_bases",
                "player": "Aaron Judge",
                "team": "NYY",
                "opponent": "BAL",
                "line": "1.5",
                "americanOdds": "-110",
                "book": "TestBook",
                "actual_value": "3",
                "hit": "1",
                "result": "win",
            }
        ],
    )

    result = FeatureStoreMaterializer(settings).materialize(date_label=date_label, season=2026)
    path = settings.data_dir / "features" / f"prop_features_{date_label}.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")

    assert result["schemaVersion"] == "feature-store-materializer.v1"
    assert result["pregameSafe"] is True
    assert result["labelsExcluded"] is True
    assert result["rows"] == 1
    assert set(postgame_label_names()).isdisjoint(header)
    assert set(header) == set(pregame_feature_names())


def test_feature_store_status_route_is_read_only_and_safe(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("feature-store status must not train models")

    monkeypatch.setattr("mlb_app.services.model_training_service.ModelTrainingService.train_market", forbidden)
    settings = make_settings(tmp_path)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/runtime/feature-store/status?date=today&season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "feature-store-materializer.v1"
    assert payload["pregameSafe"] is True
    assert payload["labelsExcluded"] is True
    assert payload["externalApiCallsMade"] is False
    assert payload["modelTrainingTriggered"] is False
