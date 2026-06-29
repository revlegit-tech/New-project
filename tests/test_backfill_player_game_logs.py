from __future__ import annotations

import csv
from pathlib import Path

import scripts.backfill_player_game_logs as backfill


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fake_collect_logs(start_date: str, end_date: str, season: int):
    assert start_date == "2026-06-23"
    assert end_date == "2026-06-23"
    assert season == 2026
    return (
        [
            {
                "season": "2026",
                "seasonPhase": "regular",
                "date": "2026-06-23",
                "gamePk": "100",
                "side": "home",
                "team": "NYY",
                "opponent": "BAL",
                "playerId": "99",
                "player": "Aaron Judge",
                "hits": "2",
                "totalBases": "5",
            },
            {
                "season": "2026",
                "seasonPhase": "regular",
                "date": "2026-06-23",
                "gamePk": "100",
                "side": "home",
                "team": "NYY",
                "opponent": "BAL",
                "playerId": "99",
                "player": "Aaron Judge",
                "hits": "2",
                "totalBases": "5",
            },
        ],
        [
            {
                "season": "2026",
                "seasonPhase": "regular",
                "date": "2026-06-23",
                "gamePk": "100",
                "side": "away",
                "team": "BAL",
                "opponent": "NYY",
                "playerId": "55",
                "player": "Example Pitcher",
                "strikeOuts": "7",
                "inningsPitched": "6.0",
            }
        ],
        [],
    )


def test_backfill_preserves_existing_rows_and_writes_schema(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "season_logs"
    batter_path = season_dir / "batter_game_logs_2026.csv"
    pitcher_path = season_dir / "pitcher_game_logs_2026.csv"
    write_rows(
        batter_path,
        ["date", "gamePk", "playerId", "player", "team", "hits"],
        [{"date": "2026-06-22", "gamePk": "90", "playerId": "1", "player": "Existing Batter", "team": "BOS", "hits": "1"}],
    )
    write_rows(
        pitcher_path,
        ["date", "gamePk", "playerId", "player", "team", "strikeOuts"],
        [{"date": "2026-06-22", "gamePk": "91", "playerId": "2", "player": "Existing Pitcher", "team": "BOS", "strikeOuts": "4"}],
    )
    monkeypatch.setattr(backfill, "collect_logs", fake_collect_logs)

    summary = backfill.run(
        start_date="2026-06-23",
        end_date="2026-06-23",
        season=2026,
        season_log_dir=season_dir,
    )

    batter_rows = read_rows(batter_path)
    pitcher_rows = read_rows(pitcher_path)
    assert summary["existingRowCounts"] == {"batter": 1, "pitcher": 1}
    assert summary["addedRows"] == {"batter": 1, "pitcher": 1}
    assert len(batter_rows) == 2
    assert len(pitcher_rows) == 2
    assert batter_rows[0]["player"] == "Existing Batter"
    assert {"season", "seasonPhase", "date", "gamePk", "playerId", "player", "team", "opponent", "hits"} <= set(
        batter_rows[0]
    )
    assert {"season", "seasonPhase", "date", "gamePk", "playerId", "player", "team", "opponent", "strikeOuts"} <= set(
        pitcher_rows[0]
    )


def test_backfill_dedupes_existing_and_fetched_duplicate_rows(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "season_logs"
    batter_path = season_dir / "batter_game_logs_2026.csv"
    write_rows(
        batter_path,
        ["date", "gamePk", "playerId", "player", "team", "hits"],
        [
            {"date": "2026-06-23", "gamePk": "100", "playerId": "99", "player": "Aaron Judge", "team": "NYY", "hits": "1"},
            {"date": "2026-06-23", "gamePk": "100", "playerId": "99", "player": "Aaron Judge", "team": "NYY", "hits": "1"},
        ],
    )
    monkeypatch.setattr(backfill, "collect_logs", fake_collect_logs)

    summary = backfill.run(
        start_date="2026-06-23",
        end_date="2026-06-23",
        season=2026,
        season_log_dir=season_dir,
    )

    assert summary["existingRowCounts"]["batter"] == 2
    assert summary["addedRows"]["batter"] == 0
    assert len(read_rows(batter_path)) == 1


def test_backfill_dry_run_does_not_write_files(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "season_logs"
    monkeypatch.setattr(backfill, "collect_logs", fake_collect_logs)

    summary = backfill.run(
        start_date="2026-06-23",
        end_date="2026-06-23",
        season=2026,
        dry_run=True,
        season_log_dir=season_dir,
    )

    assert summary["dryRun"] is True
    assert summary["addedRows"] == {"batter": 1, "pitcher": 1}
    assert not (season_dir / "batter_game_logs_2026.csv").exists()
    assert not (season_dir / "pitcher_game_logs_2026.csv").exists()
