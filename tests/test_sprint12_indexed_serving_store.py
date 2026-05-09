from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.repositories.board_snapshot_repository import BoardSnapshotRepository
from mlb_app.repositories.db import SQLiteDatabase
from mlb_app.services.playerboard_read_service import PlayerboardReadService, prop_key_for_row


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_env(tmp_path)


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "snapshotAt": datetime.now(timezone.utc).isoformat(),
        "season": 2026,
        "date": "2026-05-07",
        "market": "batter_hits",
        "marketDisplay": "Batter Hits",
        "player": "Indexed Batter",
        "team": "NYY",
        "opponent": "BOS",
        "pitcher": "Starter One",
        "line": "0.5",
        "americanOdds": "-110",
        "book": "Book A",
        "bookKey": "book_a",
        "bookCount": "1",
        "books": [],
        "finalProbabilityPercent": "58.0",
        "sportsbookImpliedPercent": "52.38",
        "finalEdgePercent": "5.62",
        "confidence": "Medium",
        "recommendation": "Watchlist",
        "missingData": [],
        "rawLabel": "Over 0.5",
        "hitRates": {},
        "recentGames": [],
    }
    row.update(overrides)
    row["propKey"] = prop_key_for_row(row)
    return row


class ExplodingCsvRepository:
    def read_current_playerboard(self, **_: Any) -> Any:  # pragma: no cover - failure path only
        raise AssertionError("CSV should not be parsed when an active SQLite board snapshot exists")


def test_playerboard_read_service_uses_active_sqlite_snapshot_before_csv(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db = SQLiteDatabase(settings.state_db_path)
    snapshot_repository = BoardSnapshotRepository(settings, db=db)
    row = _row(season=settings.current_season)
    activated = snapshot_repository.replace_active_snapshot(
        season=settings.current_season,
        date_label="2026-05-07",
        market="batter_hits",
        rows=[row],
        snapshot_at=row["snapshotAt"],
        csv_path=settings.data_dir / "playerboard" / f"playerboard_{settings.current_season}.csv",
    )

    service = PlayerboardReadService(
        repository=ExplodingCsvRepository(),  # type: ignore[arg-type]
        snapshot_repository=snapshot_repository,
        settings=settings,
    )
    snapshot = service.get_snapshot(season=settings.current_season, date_label="2026-05-07", market="batter_hits")

    assert snapshot.source == "sqlite"
    assert snapshot.snapshot_ids == (activated.id,)
    assert snapshot.rows[0]["player"] == "Indexed Batter"
    assert snapshot.row_for_prop_key(row["propKey"])["player"] == "Indexed Batter"


def test_edge_board_and_prop_detail_do_not_parse_csv_when_sqlite_is_warm(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    container = AppContainer(settings=settings)
    row = _row(season=settings.current_season)
    container.board_snapshot_repository.replace_active_snapshot(
        season=settings.current_season,
        date_label="2026-05-07",
        market="batter_hits",
        rows=[row],
        snapshot_at=row["snapshotAt"],
    )

    def explode_csv(**_: Any) -> Any:  # pragma: no cover - failure path only
        raise AssertionError("CSV fallback was called during warm SQLite serving")

    container.playerboard_read_service.repository.read_current_playerboard = explode_csv  # type: ignore[method-assign]
    client = TestClient(create_app(container=container))

    edge = client.get(f"/api/edge-board?season={settings.current_season}&date=2026-05-07&market=batter_hits&limit=10")
    assert edge.status_code == 200
    edge_payload = edge.json()
    assert edge_payload["rowCount"] == 1
    assert edge_payload["meta"]["source"] == "playerboard_snapshot"
    assert edge_payload["meta"]["snapshotSignature"]

    detail = client.get(
        f"/api/prop-detail?season={settings.current_season}&date=2026-05-07&market=batter_hits&propKey={row['propKey']}"
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["source"]["lookupMode"] == "prop_key"
    assert detail_payload["source"]["snapshot"]["source"] == "sqlite"
    assert detail_payload["detail"]["overview"]["player"] == "Indexed Batter"


def test_board_snapshot_activation_is_atomic_and_replaces_scope(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = BoardSnapshotRepository(settings)
    first = _row(season=settings.current_season, player="Old Batter", finalEdgePercent="1.0")
    second = _row(season=settings.current_season, player="New Batter", finalEdgePercent="8.0")

    old = repository.replace_active_snapshot(
        season=settings.current_season,
        date_label="2026-05-07",
        market="batter_hits",
        rows=[first],
        snapshot_at="2026-05-07T10:00:00+00:00",
    )
    new = repository.replace_active_snapshot(
        season=settings.current_season,
        date_label="2026-05-07",
        market="batter_hits",
        rows=[second],
        snapshot_at="2026-05-07T11:00:00+00:00",
    )

    assert repository.get(old.id).status == "inactive"  # type: ignore[union-attr]
    assert repository.get(new.id).status == "active"  # type: ignore[union-attr]
    read_result = repository.read_active_playerboard(season=settings.current_season, date_label="2026-05-07", market="batter_hits")
    assert read_result is not None
    assert [row["player"] for row in read_result.rows] == ["New Batter"]
