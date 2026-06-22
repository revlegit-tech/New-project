from __future__ import annotations

from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.repositories.player_metric_repository import PlayerMetricRepository
from mlb_app.repositories.statcast_repository import StatcastRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.statcast_ingestion_service import StatcastIngestionService


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


def ingestion_service(settings: Settings) -> tuple[StatcastIngestionService, StatcastRepository]:
    db = WarehouseDatabase.from_settings(settings)
    statcast = StatcastRepository(db, settings=settings)
    player_metrics = PlayerMetricRepository(db, settings=settings)
    return (
        StatcastIngestionService(
            statcast_repository=statcast,
            player_metric_repository=player_metrics,
        ),
        statcast,
    )


def pitch_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "game_date": "2026-06-22",
        "season": 2026,
        "gamePk": "game-1",
        "player_id": "607625",
        "player_name": "Test Pitcher",
        "team": "NYM",
        "opponent": "ATL",
        "pitch_type": "FF",
        "release_speed": 97.1,
        "description": "called_strike",
    }
    row.update(overrides)
    return row


def test_statcast_repository_writes_and_reads_csv_fallback(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=False)
    service, repository = ingestion_service(settings)

    result = service.ingest_rows("statcast_pitches", [pitch_row()], date_label="2026-06-22")
    rows = repository.read_rows("statcast_pitches", date_label="2026-06-22")

    assert result.mode == "csv"
    assert result.count == 1
    assert repository.csv_path("statcast_pitches", date_label="2026-06-22").exists()
    assert rows[0]["player_name"] == "Test Pitcher"
    assert rows[0]["pitch_type"] == "FF"


def test_statcast_repository_writes_and_reads_db_enabled_mode(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        db_enabled=True,
        database_url=f"sqlite:///{tmp_path / 'warehouse.sqlite3'}",
    )
    db = WarehouseDatabase.from_settings(settings)
    db.initialize()
    statcast = StatcastRepository(db, settings=settings)
    player_metrics = PlayerMetricRepository(db, settings=settings)
    service = StatcastIngestionService(
        statcast_repository=statcast,
        player_metric_repository=player_metrics,
    )

    result = service.ingest_rows("statcast_pitches", [pitch_row(player_id="999")], date_label="2026-06-22")
    rows = statcast.read_rows("statcast_pitches", date_label="2026-06-22", player_id="999")

    assert result.mode == "database"
    assert result.count == 1
    assert rows[0]["player_id"] == "999"
    assert rows[0]["game_id"] == "game-1"


def test_statcast_ingestion_empty_source_is_safe(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service, repository = ingestion_service(settings)

    result = service.ingest_rows("statcast_pitches", [], date_label="2026-06-22")

    assert result.count == 0
    assert repository.read_rows("statcast_pitches", date_label="2026-06-22") == []
