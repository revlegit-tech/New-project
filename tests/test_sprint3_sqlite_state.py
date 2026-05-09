from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.repositories.bankroll_repository import BankrollRepository
from mlb_app.repositories.db import SQLiteDatabase
from mlb_app.repositories.picks_repository import PicksRepository
from mlb_app.repositories.prediction_events_repository import PredictionEventsRepository
from mlb_app.services.bankroll_service import BankrollService
from mlb_app.services.picks_service import PicksService


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_env(tmp_path)


def test_sqlite_database_runs_migrations_and_enables_wal(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db = SQLiteDatabase(settings.state_db_path)

    versions = db.migration_versions()

    assert versions == ["0001_initial", "0002_picks", "0003_prediction_events"]
    with sqlite3.connect(settings.state_db_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "wal"


def test_bankroll_repository_round_trips_settings(tmp_path: Path) -> None:
    service = BankrollService(_settings(tmp_path))

    payload = service.update(
        {
            "bankroll": 2500,
            "defaultUnitSize": 25,
            "maxUnitsPerBet": 0.4,
            "maxBetsPerSlate": 8,
            "maxExposurePerGameUnits": 1.0,
            "maxExposurePerPlayerUnits": 0.5,
            "stakingMethod": "flat",
            "conservativeMode": False,
        }
    )

    assert payload["settings"]["bankroll"] == 2500
    assert payload["settings"]["defaultUnitSize"] == 25
    assert payload["storage"]["sourceOfTruth"] == "sqlite"
    reloaded = BankrollService(_settings(tmp_path)).get_settings()
    assert reloaded.bankroll == 2500
    assert reloaded.conservative_mode is False


def test_picks_service_writes_and_updates_sqlite_transactionally(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bankroll = BankrollService(settings)
    bankroll.update({"bankroll": 2000, "defaultUnitSize": 20, "maxUnitsPerBet": 0.25})
    service = PicksService(settings, bankroll_service=bankroll)

    created = service.create(
        {
            "date": "2026-05-07",
            "player": "Juan Soto",
            "team": "NYM",
            "opponent": "PHI",
            "market": "batter_hits",
            "line": "0.5",
            "americanOdds": "-120",
            "decisionLabel": "Potential edge",
            "readinessLabel": "Production candidate",
            "suggestedStake": "0.25u capped",
            "stakeUnits": 2.0,
        }
    )

    assert created["pick"]["stakeUnits"] == 0.25
    assert created["pick"]["stakeAmount"] == 5.0
    assert created["exposure"]["totalStakeUnits"] == 0.25

    updated = service.update({"id": created["pick"]["id"], "status": "Won", "profitUnits": 0.22})

    assert updated["pick"]["status"] == "Won"
    assert PicksRepository(settings).count() == 1
    assert service.payload()["exposure"]["profitUnits"] == 0.22


def test_legacy_json_user_state_is_imported_once_then_sqlite_is_source_of_truth(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    user_dir = settings.data_dir / "user"
    user_dir.mkdir(parents=True)
    (user_dir / "bankroll_settings.json").write_text(
        json.dumps({"settings": {"bankroll": 1500, "defaultUnitSize": 15, "maxUnitsPerBet": 0.3}}),
        encoding="utf-8",
    )
    (user_dir / "my_picks.json").write_text(
        json.dumps(
            {
                "version": "legacy",
                "picks": [
                    {
                        "id": "legacy-1",
                        "createdAt": "2026-05-07T12:00:00Z",
                        "updatedAt": "2026-05-07T12:00:00Z",
                        "date": "2026-05-07",
                        "player": "Aaron Judge",
                        "team": "NYY",
                        "opponent": "BAL",
                        "market": "batter_total_bases",
                        "line": "1.5",
                        "americanOdds": "-110",
                        "status": "Watching",
                        "stakeUnits": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    service = PicksService(settings)
    assert service.payload()["pickCount"] == 1
    assert BankrollService(settings).get_settings().bankroll == 1500

    # Mutating legacy JSON after the first import must not change app state.
    (user_dir / "my_picks.json").write_text(json.dumps({"version": "legacy", "picks": []}), encoding="utf-8")
    (user_dir / "bankroll_settings.json").write_text(
        json.dumps({"settings": {"bankroll": 999999, "defaultUnitSize": 999}}),
        encoding="utf-8",
    )

    assert PicksService(settings).payload()["pickCount"] == 1
    assert BankrollService(settings).get_settings().bankroll == 1500


def test_concurrent_pick_writes_do_not_drop_rows(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = PicksService(settings)

    def create(index: int) -> str:
        payload = service.create(
            {
                "date": "2026-05-07",
                "player": f"Player {index}",
                "team": "NYY",
                "opponent": "BAL",
                "market": "batter_hits",
                "line": "0.5",
                "americanOdds": "-110",
                "decisionLabel": "Potential edge",
                "readinessLabel": "Production candidate",
                "suggestedStake": "0.25u capped",
                "stakeUnits": 0.25,
            }
        )
        return str(payload["pick"]["id"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(create, range(20)))

    assert len(set(ids)) == 20
    assert PicksRepository(settings).count() == 20


def test_prediction_events_repository_is_append_only_audit_storage(tmp_path: Path) -> None:
    repository = PredictionEventsRepository(_settings(tmp_path))

    event = repository.append(
        {
            "modelKey": "batter_hits",
            "modelVersion": "2026.05.08.1",
            "market": "batter_hits",
            "playerId": "player-1",
            "gameId": "game-1",
            "inputHash": "input-hash",
            "outputProbability": 0.58,
            "outputEdge": 0.06,
            "artifactSha256": "abc123",
        }
    )

    assert event["id"]
    rows = repository.list_events(market="batter_hits")
    assert len(rows) == 1
    assert rows[0]["modelKey"] == "batter_hits"
    assert rows[0]["artifactSha256"] == "abc123"
