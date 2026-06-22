from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.repositories.playerboard_repository import PlayerboardRepository
from mlb_app.repositories.playerboard_snapshot_repository import PlayerboardSnapshotRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.playerboard_read_service import PlayerboardReadService


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
    }
    values.update(overrides)
    return Settings(**values)


def test_database_config_parsing(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATABASE_POOL_SIZE", "9")
    monkeypatch.setenv("DATABASE_ECHO", "1")
    monkeypatch.setenv("DB_ENABLED", "true")
    monkeypatch.setenv("DB_FALLBACK_TO_CSV", "0")

    settings = Settings.from_env(tmp_path)

    assert settings.database_url == f"sqlite:///{db_path}"
    assert settings.database_pool_size == 9
    assert settings.database_echo is True
    assert settings.db_enabled is True
    assert settings.db_fallback_to_csv is False


def test_db_disabled_playerboard_read_falls_back_to_csv(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=False)
    repository = PlayerboardRepository(settings=settings)
    repository.write_snapshot_rows(
        season=2026,
        rows=[
            {
                "date": "2026-06-22",
                "snapshotAt": "2026-06-22T15:00:00Z",
                "market": "batter_hits",
                "player": "Test Player",
                "team": "NYY",
                "opponent": "BOS",
                "line": "0.5",
                "americanOdds": "-120",
                "book": "TestBook",
            }
        ],
        replace=True,
    )

    snapshot = PlayerboardReadService(repository=repository, settings=settings).get_snapshot(
        season=2026,
        date_label="2026-06-22",
    )

    assert snapshot.source == "csv"
    assert len(snapshot.rows) == 1
    assert snapshot.rows[0]["player"] == "Test Player"


def test_playerboard_snapshot_repository_upsert_is_idempotent(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        db_enabled=True,
        database_url=f"sqlite:///{tmp_path / 'warehouse.sqlite3'}",
    )
    db = WarehouseDatabase.from_settings(settings)
    db.initialize()
    repository = PlayerboardSnapshotRepository(db, settings=settings)
    rows = [
        {
            "date": "2026-06-22",
            "snapshotAt": "2026-06-22T15:00:00Z",
            "market": "batter_hits",
            "player": "Test Player",
            "team": "NYY",
            "opponent": "BOS",
            "line": "0.5",
            "americanOdds": "-120",
            "book": "TestBook",
            "edgePercent": "4.2",
        }
    ]

    repository.upsert_snapshot(
        season=2026,
        date_label="2026-06-22",
        rows=rows,
        snapshot_at="2026-06-22T15:00:00Z",
        source_path="data/playerboard/playerboard_2026.csv",
    )
    repository.upsert_snapshot(
        season=2026,
        date_label="2026-06-22",
        rows=rows,
        snapshot_at="2026-06-22T15:00:00Z",
        source_path="data/playerboard/playerboard_2026.csv",
    )

    counts = repository.row_counts_by_market_date(season=2026, date_label="2026-06-22")
    result = repository.read_latest_playerboard(season=2026, date_label="2026-06-22")

    assert counts == {"batter_hits": 1}
    assert result is not None
    assert result.source == "database"
    assert len(result.rows) == 1
    assert result.rows[0]["player"] == "Test Player"


def test_import_csv_snapshots_dry_run_prints_counts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    playerboard = data_dir / "playerboard" / "playerboard_2026.csv"
    playerboard.parent.mkdir(parents=True)
    with playerboard.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "snapshotAt", "market", "player", "team"])
        writer.writeheader()
        writer.writerow(
            {
                "date": "2026-06-22",
                "snapshotAt": "2026-06-22T15:00:00Z",
                "market": "batter_hits",
                "player": "Test Player",
                "team": "NYY",
            }
        )
    manifest_dir = data_dir / "health" / "collector_manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "collector_manifest_2026-06-22_test.json").write_text(
        json.dumps({"run_id": "run-1", "date": "2026-06-22"}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(Path("scripts/import_csv_snapshots_to_db.py")),
            "--data-dir",
            str(data_dir),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "DRY RUN" in result.stdout
    assert "collector_manifests: 1" in result.stdout
    assert "playerboard_rows: 1" in result.stdout
    assert not (tmp_path / "warehouse.sqlite3").exists()


def test_data_status_handles_enabled_db_with_missing_url(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=True, database_url="")

    payload = DataStatusService(settings=settings).payload({"season": ["2026"]})

    assert payload["database"]["enabled"] is True
    assert payload["database"]["reachable"] is False
    assert payload["database"]["reason"] == "missing_database_url"
    assert payload["database"]["csv_fallback"]["status"] == "active_db_unreachable"


def test_data_status_endpoint_reports_unavailable_db_without_crashing(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        db_enabled=True,
        database_url="postgresql://",
        db_fallback_to_csv=True,
    )
    container = AppContainer(settings=settings)
    container.data_status_service = DataStatusService(settings=settings)
    app = create_app(container=container)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/data/status?season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["database"]["enabled"] is True
    assert payload["database"]["reachable"] is False
    assert payload["database"]["csv_fallback"]["enabled"] is True
    assert any("Warehouse database is enabled but unreachable" in warning for warning in payload["warnings"])
