from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import phase17_common as common  # noqa: E402
import phase17_enrich_game_context as enrich  # noqa: E402
from phase17_common import implied_probability_from_american, implied_runs_from_total_and_moneylines  # noqa: E402


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_implied_probability_from_american() -> None:
    assert round(implied_probability_from_american(-150) or 0, 4) == 0.6
    assert round(implied_probability_from_american(120) or 0, 4) == 0.4545


def test_implied_runs_require_real_total_and_moneylines() -> None:
    team, opp, source = implied_runs_from_total_and_moneylines(-150, 130, 8.5)
    assert team is not None and opp is not None
    assert round(team + opp, 3) == 8.5
    assert source == "moneyline_total_proxy"
    assert implied_runs_from_total_and_moneylines("", 130, 8.5) == (None, None, "")


def test_apply_context_maps_team_side() -> None:
    row = {"date": "2026-05-07", "market": "batter_hits", "team": "STL", "opponent": "SD"}
    context = {
        "home_team": "San Diego Padres",
        "away_team": "St. Louis Cardinals",
        "away_moneyline": "+130",
        "home_moneyline": "-150",
        "game_total": "8.5",
        "park_factor": "1.03",
        "_source": "unit-test",
    }
    updated, changed, fields = enrich.apply_context(row, context)
    assert changed is True
    assert updated["team_moneyline"] == "+130"
    assert updated["opponent_moneyline"] == "-150"
    assert updated["game_total"] == "8.5"
    assert updated["park_factor"] == "1.03"
    assert "team_implied_runs" in updated
    assert "team_moneyline" in fields


def test_enrich_rows_uses_local_game_context(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    playerboard = data / "playerboard" / "playerboard_2026.csv"
    game_lines = data / "warehouse" / "odds_snapshots" / "game_lines_2026-05-07.csv"
    write_csv(
        playerboard,
        [
            {
                "date": "2026-05-07",
                "market": "batter_hits",
                "player": "Test Batter",
                "team": "STL",
                "opponent": "SD",
                "line": "0.5",
            }
        ],
    )
    write_csv(
        game_lines,
        [
            {
                "home_team": "San Diego Padres",
                "away_team": "St. Louis Cardinals",
                "home_moneyline": "-150",
                "away_moneyline": "+130",
                "game_total": "8.5",
                "park_factor": "1.03",
            }
        ],
    )

    monkeypatch.setattr(common, "DATA_DIR", data)
    monkeypatch.setattr(common, "PLAYERBOARD_DIR", data / "playerboard")
    monkeypatch.setattr(common, "WAREHOUSE_DIR", data / "warehouse")
    monkeypatch.setattr(common, "AUDIT_DIR", data / "models" / "audits")
    monkeypatch.setattr(enrich, "AUDIT_DIR", data / "models" / "audits")

    result = enrich.enrich_rows(2026, "2026-05-07", markets=["batter_hits"], write=True)
    assert result["matchedRows"] == 1
    assert result["updatedRows"] == 1
    rows = common.read_csv_rows(playerboard)
    assert rows[0]["team_moneyline"] == "+130"
    assert rows[0]["opponent_moneyline"] == "-150"
    assert rows[0]["game_total"] == "8.5"
