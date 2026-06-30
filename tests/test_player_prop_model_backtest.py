from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.player_prop_model_backtest_service import PlayerPropModelBacktestService, backtest_rows, edge_bucket


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


def test_backtest_groups_by_market_and_edge_bucket(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    input_path = tmp_path / "historical.csv"
    write_csv(
        input_path,
        [
            {"market": "batter_hits", "side": "Over", "model_probability_percent": "60", "over": "1", "implied_probability_percent": "52", "american_odds": "-110"},
            {"market": "batter_hits", "side": "Over", "model_probability_percent": "45", "over": "0", "implied_probability_percent": "50", "american_odds": "-110"},
            {"market": "pitcher_strikeouts", "side": "Under", "model_probability_percent": "70", "over": "0", "implied_probability_percent": "55", "american_odds": "+120"},
        ],
    )

    report = PlayerPropModelBacktestService(settings=settings).backtest(season=2026, input_path=input_path, dry_run=True)

    assert report["summary"]["rowsEvaluated"] == 3
    assert set(report["summary"]["markets"]) == {"batter_hits", "pitcher_strikeouts"}
    batter = report["summary"]["markets"]["batter_hits"]
    assert batter["sampleSize"] == 2
    assert len(batter["edgeBuckets"]) == 2


def test_edge_buckets_are_computed() -> None:
    assert edge_bucket(0.08) == "5% to 10%"
    assert edge_bucket(-0.02) == "-5% to 0%"


def test_roi_is_computed_only_when_odds_are_available() -> None:
    rows = backtest_rows(
        [
            {"market": "batter_hits", "model_probability_percent": "60", "over": "1", "american_odds": "+150"},
            {"market": "batter_hits", "model_probability_percent": "40", "over": "0"},
        ]
    )

    assert rows[0]["roi"] == 1.5
    assert rows[1]["roi"] is None
