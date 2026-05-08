from __future__ import annotations

import csv
from pathlib import Path

from tools import run_daily_slate_pipeline
from tools import validate_daily_slate


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_validate_daily_slate_accepts_canonical_rows_and_merged_books(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_daily_slate, "ROOT", tmp_path)
    date_label = "2026-05-07"
    _write_csv(
        tmp_path / "data" / "odds" / f"propline_props_{date_label}.csv",
        ["player", "market", "line", "americanOdds"],
        [{"player": "Nick Gonzales", "market": "batter_hits", "line": "0.5", "americanOdds": "+100"}],
    )
    _write_csv(
        tmp_path / "data" / "playerboard" / "playerboard_2026.csv",
        ["date", "player", "market", "baseMarket", "line", "rawLabel", "bookCount", "hitRates", "recentGames"],
        [
            {
                "date": date_label,
                "player": "Nick Gonzales",
                "market": "batter_hits",
                "baseMarket": "batter_hits",
                "line": "0.5",
                "rawLabel": "Over",
                "bookCount": "4",
                "hitRates": '{"L5": 60}',
                "recentGames": "[]",
            }
        ],
    )

    payload = validate_daily_slate.validate_slate(date_label, 2026)

    assert payload["ok"] is True
    assert payload["propRows"] == 1
    assert payload["playerboardRowsForDate"] == 1
    assert payload["rowsWithMergedBooks"] == 1
    assert payload["rowsWithHitRates"] == 1
    assert payload["duplicateGroupCount"] == 0


def test_validate_daily_slate_flags_duplicate_player_market_line_direction(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_daily_slate, "ROOT", tmp_path)
    date_label = "2026-05-07"
    _write_csv(
        tmp_path / "data" / "odds" / f"propline_props_{date_label}.csv",
        ["player", "market", "line", "americanOdds"],
        [{"player": "Nick Gonzales", "market": "batter_hits", "line": "0.5", "americanOdds": "+100"}],
    )
    rows = [
        {"date": date_label, "player": "Nick Gonzales", "market": "batter_hits", "baseMarket": "batter_hits", "line": "0.5", "rawLabel": "Yes"},
        {"date": date_label, "player": "Nick Gonzales", "market": "batter_hits", "baseMarket": "batter_hits", "line": "0.5", "rawLabel": "Over"},
    ]
    _write_csv(
        tmp_path / "data" / "playerboard" / "playerboard_2026.csv",
        ["date", "player", "market", "baseMarket", "line", "rawLabel"],
        rows,
    )

    payload = validate_daily_slate.validate_slate(date_label, 2026)

    assert payload["ok"] is False
    assert payload["duplicateGroupCount"] == 1
    assert "duplicate" in " ".join(payload["warnings"]).lower()


def test_daily_slate_pipeline_dry_run_has_required_refresh_step():
    parser = run_daily_slate_pipeline.build_parser()
    args = parser.parse_args([
        "--date",
        "2026-05-07",
        "--season",
        "2026",
        "--dry-run",
        "--skip-schedule",
        "--skip-weather",
        "--skip-odds-movement",
    ])

    payload = run_daily_slate_pipeline.run_pipeline(args).as_dict()

    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["date"] == "2026-05-07"
    assert [step["name"] for step in payload["steps"]] == ["propline_and_playerboard_refresh"]
    assert payload["steps"][0]["required"] is True
    assert payload["steps"][0]["skipped"] is True
