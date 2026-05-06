from __future__ import annotations

"""Merge sportsbook archive game-odds features into prop training rows.

This script adds game-level betting context to your historical prop rows:
- team_moneyline
- opponent_moneyline
- game_total
- open_team_moneyline
- close_team_moneyline
- moneyline_move
- total_move
- moneyline_implied_probability
- favorite_status
- team_implied_runs
- opponent_implied_runs
- opponent_implied_runs_proxy

Usage:
    python merge_game_odds_features.py \
      --props data/training/historical_props.csv \
      --game-odds data/imports/game_odds_archive.csv \
      --out data/training/historical_props_with_game_odds.csv

Expected game odds CSV columns can use common aliases:

Required-ish:
    date, team, opponent

Useful:
    team_moneyline, opponent_moneyline, game_total,
    open_team_moneyline, close_team_moneyline,
    open_game_total, close_game_total,
    team_implied_runs, opponent_implied_runs

If exact implied run columns are not present, the script creates a simple proxy from
game_total + moneyline favorite/underdog status.
"""

import argparse
import csv
import re
from pathlib import Path
from typing import Any

OUTPUT_COLUMNS_TO_ADD = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "favorite_status",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
]


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def normalize_team(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "CWS": "CHW",
        "KC": "KCR",
        "SD": "SDP",
        "SF": "SFG",
        "TB": "TBR",
        "WSH": "WSN",
        "AZ": "ARI",
        "OAK": "ATH",
    }
    return aliases.get(text, text[:3])


def first_value(row: dict[str, Any], aliases: list[str], default: Any = "") -> Any:
    normalized = {normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        key = normalize_key(alias)
        if key in normalized and str(normalized[key]).strip() != "":
            return normalized[key]
    return default


def to_float(value: Any, default: float = 0.0) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def implied_probability_from_american(odds: float) -> float:
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return 0.5


def favorite_status(team_ml: float, opponent_ml: float) -> str:
    if not team_ml and not opponent_ml:
        return ""
    if team_ml < opponent_ml:
        return "favorite"
    if team_ml > opponent_ml:
        return "underdog"
    return "even"


def implied_runs_proxy(game_total: float, team_ml: float, opponent_ml: float) -> tuple[float, float]:
    """Return rough team/opponent implied runs from total + ML.

    This is a proxy, not a true sportsbook team total. If your archive provides
    team_implied_runs/opponent_implied_runs, those values are preferred.
    """
    if game_total <= 0:
        return 0.0, 0.0

    team_prob = implied_probability_from_american(team_ml) if team_ml else 0.5
    opp_prob = implied_probability_from_american(opponent_ml) if opponent_ml else 0.5

    total_prob = team_prob + opp_prob
    if total_prob > 0:
        team_prob /= total_prob

    adjustment = max(min((team_prob - 0.5) * 2.0, 0.18), -0.18)
    team_runs = game_total * (0.5 + adjustment)
    opponent_runs = game_total - team_runs
    return round(team_runs, 3), round(opponent_runs, 3)


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def odds_record_for_team(row: dict[str, Any]) -> dict[str, Any]:
    team = normalize_team(first_value(row, ["team", "Team", "tm", "away_team", "home_team"]))
    opponent = normalize_team(first_value(row, ["opponent", "Opponent", "opp"]))
    date = str(first_value(row, ["date", "game_date", "Date"]))[:10]

    team_ml = to_float(first_value(row, ["team_moneyline", "moneyline", "ml", "close_team_moneyline", "closing_moneyline"]))
    opponent_ml = to_float(first_value(row, ["opponent_moneyline", "opp_moneyline", "opponent_ml"]))
    game_total = to_float(first_value(row, ["game_total", "total", "close_total", "closing_total"]))

    open_team_ml = to_float(first_value(row, ["open_team_moneyline", "opening_team_moneyline", "open_moneyline"]))
    close_team_ml = to_float(first_value(row, ["close_team_moneyline", "closing_team_moneyline", "team_moneyline", "moneyline", "ml"]))
    open_total = to_float(first_value(row, ["open_game_total", "opening_total", "open_total"]))
    close_total = to_float(first_value(row, ["close_game_total", "closing_total", "game_total", "total"]))

    team_runs = to_float(first_value(row, ["team_implied_runs", "team_total", "implied_team_total"]))
    opponent_runs = to_float(first_value(row, ["opponent_implied_runs", "opponent_team_total", "opp_implied_runs"]))

    proxy_team_runs, proxy_opponent_runs = implied_runs_proxy(game_total, team_ml, opponent_ml)

    return {
        "date": date,
        "team": team,
        "opponent": opponent,
        "team_moneyline": team_ml,
        "opponent_moneyline": opponent_ml,
        "game_total": game_total,
        "open_team_moneyline": open_team_ml,
        "close_team_moneyline": close_team_ml,
        "moneyline_move": close_team_ml - open_team_ml if open_team_ml and close_team_ml else 0,
        "open_game_total": open_total,
        "close_game_total": close_total,
        "total_move": close_total - open_total if open_total and close_total else 0,
        "moneyline_implied_probability": implied_probability_from_american(team_ml) if team_ml else 0.5,
        "favorite_status": favorite_status(team_ml, opponent_ml),
        "team_implied_runs": team_runs or proxy_team_runs,
        "opponent_implied_runs": opponent_runs or proxy_opponent_runs,
        "opponent_implied_runs_proxy": proxy_opponent_runs,
    }


def build_odds_index(game_odds_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}

    for raw in game_odds_rows:
        record = odds_record_for_team(raw)
        if not record["date"] or not record["team"] or not record["opponent"]:
            continue

        index[(record["date"], record["team"], record["opponent"])] = record

        reverse_team_runs = record["opponent_implied_runs"]
        reverse_opp_runs = record["team_implied_runs"]
        reverse = {
            **record,
            "team": record["opponent"],
            "opponent": record["team"],
            "team_moneyline": record["opponent_moneyline"],
            "opponent_moneyline": record["team_moneyline"],
            "moneyline_implied_probability": implied_probability_from_american(record["opponent_moneyline"]) if record["opponent_moneyline"] else 0.5,
            "favorite_status": favorite_status(record["opponent_moneyline"], record["team_moneyline"]),
            "team_implied_runs": reverse_team_runs,
            "opponent_implied_runs": reverse_opp_runs,
            "opponent_implied_runs_proxy": reverse_opp_runs,
        }
        index[(reverse["date"], reverse["team"], reverse["opponent"])] = reverse

    return index


def merge_features(props_path: Path, game_odds_path: Path, output_path: Path) -> dict[str, Any]:
    prop_rows = load_csv(props_path)
    odds_rows = load_csv(game_odds_path)
    odds_index = build_odds_index(odds_rows)

    merged: list[dict[str, Any]] = []
    matched = 0

    for row in prop_rows:
        date = str(first_value(row, ["date", "game_date", "Date"]))[:10]
        team = normalize_team(first_value(row, ["team", "Team", "tm"]))
        opponent = normalize_team(first_value(row, ["opponent", "Opponent", "opp"]))

        features = odds_index.get((date, team, opponent), {})
        if features:
            matched += 1

        merged_row = dict(row)
        for column in OUTPUT_COLUMNS_TO_ADD:
            merged_row[column] = features.get(column, "")
        merged.append(merged_row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(prop_rows[0].keys()) if prop_rows else []
    for column in OUTPUT_COLUMNS_TO_ADD:
        if column not in fieldnames:
            fieldnames.append(column)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in merged:
            writer.writerow({column: row.get(column, "") for column in fieldnames})

    return {
        "props": str(props_path),
        "gameOdds": str(game_odds_path),
        "output": str(output_path),
        "propRows": len(prop_rows),
        "gameOddsRows": len(odds_rows),
        "matchedRows": matched,
        "unmatchedRows": len(prop_rows) - matched,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge sportsbook game-odds archive features into prop training rows.")
    parser.add_argument("--props", default="data/training/historical_props.csv")
    parser.add_argument("--game-odds", required=True)
    parser.add_argument("--out", default="data/training/historical_props_with_game_odds.csv")
    args = parser.parse_args()

    summary = merge_features(Path(args.props), Path(args.game_odds), Path(args.out))
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
