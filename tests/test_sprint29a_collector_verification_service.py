from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.collector_verification_service import CollectorVerificationService, classify_collector_state
from mlb_app.services.playerboard_read_service import prop_key_for_row


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    return replace(settings, current_season=2026, db_enabled=True, database_url=f"sqlite:///{settings.state_db_path}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) or ["date"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def board_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "snapshotAt": datetime.now(timezone.utc).isoformat(),
        "season": 2026,
        "date": "2026-06-24",
        "market": "batter_hits",
        "marketDisplay": "Batter Hits",
        "player": "Verification Batter",
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


def test_classify_collector_state() -> None:
    assert classify_collector_state(props_rows=10, active_playerboard_rows=5, edge_board_rows=3, odds_snapshot_count=1) == "ok"
    assert classify_collector_state(props_rows=10, active_playerboard_rows=0, edge_board_rows=0, odds_snapshot_count=1) == "partial"
    assert classify_collector_state(props_rows=0, active_playerboard_rows=0, edge_board_rows=0, odds_snapshot_count=0) == "failed"
    assert (
        classify_collector_state(
            props_rows=0,
            active_playerboard_rows=0,
            edge_board_rows=0,
            odds_snapshot_count=0,
            checking_today=True,
            latest_active_date="2026-06-23",
            target_date="2026-06-24",
        )
        == "stale"
    )


def test_service_handles_missing_files_without_throwing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    container = AppContainer(settings=settings)
    service = CollectorVerificationService(
        settings=settings,
        board_snapshot_repository=container.board_snapshot_repository,
        edge_board_service=container.edge_board_service,
    )

    payload = service.payload(date_label="2026-06-24", season=2026)

    assert payload["schemaVersion"] == "collector-check.v1"
    assert payload["status"] in {"failed", "stale"}
    assert payload["checks"]["propsFile"]["ok"] is False
    assert payload["checks"]["activePlayerboard"]["ok"] is False
    assert payload["recommendations"]


def test_service_reports_saved_props_active_board_and_edge_rows(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    container = AppContainer(settings=settings)
    date_label = "2026-06-24"
    write_csv(settings.data_dir / "odds" / f"propline_props_{date_label}.csv", [{"date": date_label, "market": "batter_hits"}])
    write_csv(
        settings.data_dir / "warehouse" / "odds_snapshots" / f"propline_props_{date_label}_run-1.csv",
        [{"date": date_label, "market": "batter_hits"}],
    )
    row = board_row(date=date_label, season=2026)
    container.board_snapshot_repository.replace_active_snapshot(
        season=2026,
        date_label=date_label,
        market="batter_hits",
        rows=[row],
        snapshot_at=row["snapshotAt"],
    )
    service = CollectorVerificationService(
        settings=settings,
        board_snapshot_repository=container.board_snapshot_repository,
        edge_board_service=container.edge_board_service,
    )

    payload = service.payload(date_label=date_label, season=2026)

    assert payload["status"] == "ok"
    assert payload["checks"]["propsFile"]["rows"] == 1
    assert payload["checks"]["activePlayerboard"]["rows"] == 1
    assert payload["checks"]["edgeBoard"]["rows"] == 1
