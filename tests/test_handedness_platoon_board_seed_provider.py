from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.context_sources.handedness_platoon_context_provider import HandednessPlatoonContextProvider


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


def board_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-30",
        "season": "2026",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BOS",
        "pitcher": "Chris Sale",
        "market": "batter_hits",
        "side": "Over",
        "line": "0.5",
    }
    row.update(overrides)
    return row


def test_handedness_provider_seeds_from_current_board_batters_and_dedupes_markets(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            board_row(market="batter_hits"),
            board_row(market="batter_total_bases"),
            board_row(player="Chris Sale Strikeouts Thrown", team="BOS", opponent="NYY", market="pitcher_strikeouts"),
            board_row(date="2026-06-29", player="Juan Soto", team="NYM", opponent="ATL"),
        ],
    )
    write_csv(
        settings.data_dir / "warehouse" / "season_logs" / "batter_game_logs_2026.csv",
        [
            {
                "date": "2026-06-29",
                "season": "2026",
                "player": "Aaron Judge",
                "team": "NYY",
                "opponent": "TOR",
                "bats": "R",
                "p_throws": "L",
                "plateAppearances": "4",
                "atBats": "4",
                "hits": "2",
                "strikeOuts": "1",
            }
        ],
    )
    write_csv(
        settings.data_dir / "warehouse" / "season_logs" / "pitcher_game_logs_2026.csv",
        [
            {
                "date": "2026-06-29",
                "season": "2026",
                "player": "Chris Sale",
                "team": "BOS",
                "throws": "L",
                "batter_hand": "R",
                "battersFaced": "20",
                "hits": "5",
            }
        ],
    )

    result = HandednessPlatoonContextProvider(settings).materialize(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.status == "ok"
    assert len(rows) == 1
    assert rows[0]["player"] == "Aaron Judge"
    assert rows[0]["team"] == "NYY"
    assert rows[0]["opponent"] == "BOS"
    assert rows[0]["seedSource"] == "playerboard"
    assert rows[0]["seedMarketCount"] == "2"
    assert rows[0]["seedRowCount"] == "2"
    assert rows[0]["batter_hand"] == "R"
    assert rows[0]["pitcher_hand"] == "L"
    assert rows[0]["batter_avg_vs_hand"] == "0.5"
    assert rows[0]["pregameSafe"] == "True"
    assert rows[0]["labelsExcluded"] == "True"
    assert result.diagnostics["providerSourceMode"] == "playerboard"
    assert result.diagnostics["providerSeedRows"] == 3
    assert result.diagnostics["providerSeedBatterRows"] == 2
    assert result.diagnostics["providerSeedPitcherRows"] == 1
    assert result.diagnostics["contextRowsGeneratedFromBoard"] == 1
    assert result.diagnostics["contextRowsDeduped"] == 1
    assert result.diagnostics["boardSeedSkipReasons"]["role_not_applicable"] == 1


def test_handedness_provider_emits_board_rows_when_enrichment_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(settings.data_dir / "playerboard" / "playerboard_2026.csv", [board_row()])

    result = HandednessPlatoonContextProvider(settings).materialize(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.status == "partial"
    assert rows[0]["player"] == "Aaron Judge"
    assert rows[0]["batter_hand"] == ""
    assert rows[0]["pitcher_hand"] == ""
    assert "batter history unavailable" in rows[0]["warnings"]
    assert "split stats unavailable" in rows[0]["warnings"]
    assert result.diagnostics["contextRowsWithBatterHand"] == 0
    assert result.diagnostics["contextRowsWithSplitStats"] == 0


def test_handedness_provider_does_not_use_stale_schedule_logs_as_primary_seed(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "warehouse" / "season_logs" / "batter_game_logs_2026.csv",
        [{"date": "2026-06-29", "player": "Stale Batter", "team": "DET", "opponent": "HOU", "bats": "R"}],
    )

    result = HandednessPlatoonContextProvider(settings).materialize(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.status == "missing"
    assert rows == []
    assert result.diagnostics["providerSourceMode"] == "none"
    assert result.diagnostics["contextRowsGenerated"] == 0
