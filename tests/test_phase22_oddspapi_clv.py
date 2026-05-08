from __future__ import annotations

import csv
from pathlib import Path

from tools.phase22_oddspapi_clv import (
    apply_provider_rows_to_context,
    decimal_to_american,
    extract_clv_from_payload,
    team_key,
)


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_team_key_aliases():
    assert team_key("San Diego Padres") == "SDP"
    assert team_key("St. Louis Cardinals") == "STL"
    assert team_key("KC") == "KCR"


def test_decimal_to_american():
    assert decimal_to_american(2.5) == 150
    assert decimal_to_american(1.5) == -200


def test_apply_provider_rows_to_context(tmp_path: Path):
    path = tmp_path / "game_context_2026-05-07.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "team", "opponent", "team_moneyline", "game_total"])
        writer.writeheader()
        writer.writerow({"date": "2026-05-07", "team": "SDP", "opponent": "STL", "team_moneyline": "-102", "game_total": "7.5"})
    result = apply_provider_rows_to_context(path, [{
        "team_key": "SDP",
        "opponent_key": "STL",
        "fixture_id": "id1",
        "fixture_status": "PreMatch",
        "bookmakers": "pinnacle",
        "open_team_moneyline": "-110",
        "close_team_moneyline": "-102",
        "moneyline_move": "8",
        "open_game_total": "8",
        "close_game_total": "7.5",
        "total_move": "-0.5",
    }])
    rows = read_rows(path)
    assert result["updatedRows"] == 1
    assert rows[0]["oddspapi_fixture_id"] == "id1"
    assert rows[0]["line_movement_source"] == "oddspapi_clv"
    assert rows[0]["moneyline_move"] == "8"


def test_extract_clv_payload_when_outcome_maps_to_team():
    payload = {
        "odds": {
            "pinnacle": {
                "x": {
                    "marketName": "Moneyline",
                    "outcomeName": "San Diego Padres",
                    "olv": {"priceAmerican": -110},
                    "clv": {"priceAmerican": -102},
                }
            }
        }
    }
    result = extract_clv_from_payload(payload, "SDP", "STL")
    assert result["open_team_moneyline"] == "-110"
    assert result["close_team_moneyline"] == "-102"
    assert result["moneyline_move"] == "8"
