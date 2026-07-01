from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.player_handedness_lookup_service import PlayerHandednessLookupService


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


def test_handedness_lookup_resolves_batter_hand_from_local_mapping(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "cache" / "incremental_stats" / "batter_game_logs_2026.csv",
        [{"date": "2026-06-29", "playerId": "592450", "player": "Aaron Judge", "team": "NYY", "bats": "R"}],
    )

    result = PlayerHandednessLookupService(settings, season=2026, date_label="2026-06-30").lookup(
        role="batter",
        player_id="592450",
        player_name="Aaron Judge",
        team="NYY",
    )

    assert result.batter_hand == "R"
    assert result.confidence == "high"
    assert result.warnings == []


def test_handedness_lookup_resolves_pitcher_hand_from_local_mapping(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "cache" / "incremental_stats" / "pitcher_game_logs_2026.csv",
        [{"date": "2026-06-29", "playerId": "519242", "player": "Chris Sale", "team": "BOS", "throws": "L"}],
    )

    result = PlayerHandednessLookupService(settings, season=2026, date_label="2026-06-30").lookup(
        role="pitcher",
        player_id="519242",
        player_name="Chris Sale",
        team="BOS",
    )

    assert result.pitcher_hand == "L"
    assert result.confidence == "high"


def test_handedness_lookup_rejects_ambiguous_name_only_matches(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "cache" / "incremental_stats" / "batter_game_logs_2026.csv",
        [
            {"date": "2026-06-29", "playerId": "1", "player": "Test Player", "team": "NYY", "bats": "R"},
            {"date": "2026-06-29", "playerId": "2", "player": "Test Player", "team": "BOS", "bats": "L"},
        ],
    )

    result = PlayerHandednessLookupService(settings, season=2026, date_label="2026-06-30").lookup(
        role="batter",
        player_name="Test Player",
    )

    assert result.batter_hand == ""
    assert "ambiguous_batter_hand_name_only_match" in result.warnings


def test_handedness_lookup_preserves_null_when_no_source_exists(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    result = PlayerHandednessLookupService(settings, season=2026, date_label="2026-06-30").lookup(
        role="batter",
        player_name="Missing Player",
        team="NYY",
    )

    assert result.batter_hand == ""
    assert result.confidence == "unknown"
    assert "batter_hand_not_found" in result.warnings
