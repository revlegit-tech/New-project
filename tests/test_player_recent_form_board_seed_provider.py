from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.context_sources.mlb_stats_context_provider import MLBStatsContextProvider


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        current_season=2026,
        db_enabled=False,
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def test_player_recent_form_seeds_from_current_board_batter_rows(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            {"date": "2026-06-30", "season": "2026", "market": "batter_hits", "player": "Aaron Judge", "team": "NYY", "opponent": "BOS"},
            {"date": "2026-06-30", "season": "2026", "market": "pitcher_strikeouts", "player": "Gerrit Cole", "team": "NYY", "opponent": "BOS"},
        ],
    )
    write_csv(
        settings.data_dir / "cache" / "incremental_stats" / "batter_game_logs_2026.csv",
        [{"date": "2026-06-29", "season": "2026", "player": "Aaron Judge", "team": "NYY", "atBats": "4", "hits": "2", "totalBases": "3"}],
    )

    result = MLBStatsContextProvider(settings).player_recent_form(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.rows == 1
    assert rows[0]["player"] == "Aaron Judge"
    assert rows[0]["subjectRole"] == "batter"
    assert rows[0]["rolling_avg_5"] == "2.0"
    assert result.diagnostics["providerSourceMode"] == "playerboard"
    assert result.diagnostics["providerSeedBatterRows"] == 1
    assert result.diagnostics["providerSeedPitcherRows"] == 1
    assert result.diagnostics["boardSeedSkipReasons"]["role_not_applicable"] == 1


def test_player_recent_form_emits_board_rows_when_history_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [{"date": "2026-06-30", "season": "2026", "market": "batter_hits", "player": "Aaron Judge", "team": "NYY", "opponent": "BOS"}],
    )

    result = MLBStatsContextProvider(settings).player_recent_form(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.rows == 1
    assert rows[0]["recent_games"] == "0"
    assert rows[0]["rolling_avg_5"] == ""
    assert rows[0]["pregameSafe"] == "True"
    assert rows[0]["labelsExcluded"] == "True"
    assert "missing_historical_data" in rows[0]["warnings"]
    assert result.diagnostics["playerRowsMissingHistoricalData"] == 1


def test_player_recent_form_excludes_same_day_future_and_bad_dates(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [{"date": "2026-06-30", "season": "2026", "market": "batter_hits", "player": "Aaron Judge", "team": "NYY", "opponent": "BOS"}],
    )
    write_csv(
        settings.data_dir / "cache" / "incremental_stats" / "batter_game_logs_2026.csv",
        [
            {"game_date": "06/28/2026", "season": "2026", "player": "Aaron Judge", "team": "NYY", "atBats": "4", "hits": "1"},
            {"game_date": "2026-06-30", "season": "2026", "player": "Aaron Judge", "team": "NYY", "atBats": "4", "hits": "4"},
            {"game_date": "2026-07-01", "season": "2026", "player": "Aaron Judge", "team": "NYY", "atBats": "4", "hits": "4"},
            {"game_date": "not-a-date", "season": "2026", "player": "Aaron Judge", "team": "NYY", "atBats": "4", "hits": "4"},
        ],
    )

    result = MLBStatsContextProvider(settings).player_recent_form(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert rows[0]["recent_games"] == "1"
    assert rows[0]["rolling_avg_5"] == "1.0"
    assert result.diagnostics["historicalRowsBeforeTargetDate"] == 1
    assert result.diagnostics["historicalRowsRejectedSameDay"] == 1
    assert result.diagnostics["historicalRowsRejectedFuture"] == 1
    assert result.diagnostics["historicalRowsRejectedInvalidDate"] == 1
