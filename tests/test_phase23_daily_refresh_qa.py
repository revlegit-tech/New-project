from __future__ import annotations

import csv
import json
from pathlib import Path

from tools import phase23_daily_refresh_qa as qa


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_coverage_counts_non_empty_values() -> None:
    rows = [{"a": "1", "b": ""}, {"a": "2", "b": "x"}]
    result = qa.coverage(rows, ["a", "b"])
    assert result[0]["coverage"] == 1.0
    assert result[1]["coverage"] == 0.5


def test_phase23_report_ok_for_complete_fixture_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(qa, "ROOT", tmp_path)
    monkeypatch.setattr(qa, "DATA", tmp_path / "data")
    monkeypatch.setattr(qa, "AUDIT_DIR", tmp_path / "data" / "warehouse" / "audits")

    date = "2026-05-08"
    season = 2026
    context_row = {
        "date": date,
        "team": "cincinnati reds",
        "opponent": "houston astros",
        "team_moneyline": "-115",
        "opponent_moneyline": "115",
        "game_total": "9",
        "moneyline_implied_probability": "0.53",
        "team_implied_runs": "4.58",
        "opponent_implied_runs": "4.42",
        "weather_temperature_f": "71.8",
        "weather_wind_mph": "13",
        "weather_humidity": "50",
        "weather_wind_direction": "SSW",
        "roof_status": "open_air",
        "open_team_moneyline": "-115",
        "close_team_moneyline": "-115",
        "moneyline_move": "0",
        "open_game_total": "9",
        "close_game_total": "9",
        "total_move": "0",
        "line_movement_source": "phase19_observed_first_latest_snapshot",
        "line_movement_status": "ready",
        "oddspapi_fixture_id": "id1",
        "oddspapi_provider_status": "fixture_matched_no_clv",
        "oddspapi_bookmakers": "fanduel",
    }
    write_csv(qa.DATA / "odds" / f"propline_props_{date}.csv", [{"date": date, "player": "A"}])
    write_csv(qa.DATA / "warehouse" / "game_context" / f"game_context_{date}.csv", [context_row])
    write_csv(qa.DATA / "warehouse" / "game_context" / f"game_context_markets_{date}.csv", [{"date": date, "team": "cincinnati reds"}])
    write_csv(qa.DATA / "playerboard" / f"playerboard_{season}.csv", [{
        "date": date,
        "player": "A",
        "market": "batter_hits",
        "team": "CIN",
        "opponent": "HOU",
        "americanOdds": "100",
    }])
    qa.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (qa.AUDIT_DIR / f"phase22_oddspapi_clv_{date}.json").write_text(json.dumps({"status": "warning", "fixtureCount": 15}), encoding="utf-8")
    (qa.AUDIT_DIR / f"phase22_v3_fixture_metadata_fallback_{date}.json").write_text(json.dumps({"status": "ok", "fixtureCount": 15, "contextRows": 1, "matchedRows": 1, "unmatchedPairs": []}), encoding="utf-8")
    (qa.AUDIT_DIR / f"phase21_daily_refresh_{date}_morning.json").write_text(json.dumps({"collector": {"status": "ok"}}), encoding="utf-8")

    report = qa.check_artifacts(date, season)
    assert report["status"] == "ok"
    assert report["providerAudits"]["phase22FixtureMetadataFallback"]["matchedRows"] == 1
