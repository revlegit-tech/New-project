from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("phase21_freshness_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_alias_coverage_counts_camel_case_fields() -> None:
    module = load_module(Path("tools/phase21_freshness_report.py"))
    rows = [
        {
            "player": "A",
            "market": "batter_hits",
            "team": "SDP",
            "opponent": "STL",
            "americanOdds": "-102",
            "bookCount": "3",
            "book": "DraftKings",
        }
    ]
    payload = module.coverage(rows, ["american_odds", "sportsbook_count", "best_book"])
    by_field = {item["field"]: item for item in payload["fields"]}
    assert by_field["american_odds"]["coverage"] == 1.0
    assert by_field["sportsbook_count"]["coverage"] == 1.0
    assert by_field["best_book"]["coverage"] == 1.0


def test_context_alias_coverage_counts_camel_case_fields() -> None:
    module = load_module(Path("tools/phase21_freshness_report.py"))
    rows = [
        {
            "teamMoneyline": "-102",
            "opponentMoneyline": "+102",
            "gameTotal": "7.5",
            "teamImpliedRuns": "3.76",
            "weatherWindDirection": "NW",
            "roofStatus": "open_air",
        }
    ]
    payload = module.coverage(rows, [
        "team_moneyline",
        "opponent_moneyline",
        "game_total",
        "team_implied_runs",
        "weather_wind_direction",
        "roof_status",
    ])
    assert all(item["coverage"] == 1.0 for item in payload["fields"])
