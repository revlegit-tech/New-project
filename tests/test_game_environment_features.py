from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mlb_app.config import Settings
from mlb_app.repositories.game_environment_repository import GameEnvironmentRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.game_environment_feature_service import (
    GameEnvironmentFeatureService,
    normalize_game_environment_row,
    safe_game_environment_feature_names,
)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    values = {
        "root_dir": tmp_path,
        "public_dir": tmp_path / "public",
        "data_dir": data_dir,
        "model_dir": model_dir,
        "model_registry_path": model_dir / "model_registry.json",
        "current_season": 2026,
        "db_path": data_dir / "state.sqlite3",
        "db_enabled": False,
        "db_fallback_to_csv": True,
        "database_url": "",
    }
    values.update(overrides)
    return Settings(**values)


def environment_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-22",
        "season": 2026,
        "game_id": "game-1",
        "home_team": "NYY",
        "away_team": "BAL",
        "park": "Yankee Stadium",
        "park_factor_runs": 1.04,
        "park_factor_hr_lhh": 1.12,
        "park_factor_hr_rhh": 1.01,
        "temperature": 78,
        "wind_speed": 8,
        "wind_direction": "out",
        "wind_out_to_cf": 0.2,
        "humidity": 62,
        "roof_status": "open",
        "altitude": 54,
        "game_time_local": "19:05",
        "day_night": "night",
        "umpire_if_available": "Test Umpire",
    }
    row.update(overrides)
    return row


def test_game_environment_schema_supports_requested_fields() -> None:
    names = set(safe_game_environment_feature_names())

    assert {"park", "park_factor_runs", "temperature", "wind_out_to_cf", "umpire_if_available"} <= names


def test_game_environment_repository_writes_and_reads_csv_fallback(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    db = WarehouseDatabase.from_settings(settings)
    repository = GameEnvironmentRepository(db, settings=settings)
    service = GameEnvironmentFeatureService(repository)

    result = service.upsert_rows("game_environment_daily", [environment_row()], date_label="2026-06-22")
    rows = repository.read_rows("game_environment_daily", date_label="2026-06-22", game_id="game-1")

    assert result.mode == "csv"
    assert rows[0]["park"] == "Yankee Stadium"
    assert rows[0]["park_factor_runs"] == "1.04"


def test_game_environment_repository_writes_and_reads_db_enabled_mode(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        db_enabled=True,
        database_url=f"sqlite:///{tmp_path / 'warehouse.sqlite3'}",
    )
    db = WarehouseDatabase.from_settings(settings)
    db.initialize()
    repository = GameEnvironmentRepository(db, settings=settings)
    service = GameEnvironmentFeatureService(repository)

    result = service.upsert_rows("game_environment_daily", [environment_row(game_id="game-db")], date_label="2026-06-22")
    rows = repository.read_rows("game_environment_daily", date_label="2026-06-22", game_id="game-db")

    assert result.mode == "database"
    assert rows[0]["game_id"] == "game-db"
    assert rows[0]["park_factor_hr_lhh"] == 1.12


def test_game_environment_leakage_guard_rejects_final_score_fields() -> None:
    with pytest.raises(ValueError):
        normalize_game_environment_row(
            environment_row(home_score=5, away_score=3, game_status="Final"),
            dataset="game_environment_daily",
        )


def test_game_environment_empty_source_is_safe(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repository = GameEnvironmentRepository(WarehouseDatabase.from_settings(settings), settings=settings)
    service = GameEnvironmentFeatureService(repository)

    assert service.normalize_rows([], dataset="game_environment_daily") == []
    assert service.read_rows("game_environment_daily", date_label="2026-06-22") == []
