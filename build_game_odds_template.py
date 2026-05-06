from __future__ import annotations

"""Build a game-odds template CSV for every MLB game on a date.

Usage:
    python build_game_odds_template.py --date 2026-05-03

This writes:
    data/imports/game_odds_template_2026-05-03.csv

The template contains one row per team/opponent pairing so you can fill odds
for both sides of every game.
"""

import argparse
import csv
import json
import urllib.request
from pathlib import Path
from typing import Any

MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "data" / "imports"

COLUMNS = [
    "date",
    "team",
    "opponent",
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "open_game_total",
    "close_game_total",
]

TEAM_NAME_TO_ABBR = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SDP",
    "San Francisco Giants": "SFG",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def mlb_schedule(date_label: str) -> list[dict[str, Any]]:
    params = f"sportId=1&date={date_label}"
    payload = fetch_json(f"{MLB_STATS_API_BASE}/schedule?{params}")
    games: list[dict[str, Any]] = []
    for day in payload.get("dates", []):
        games.extend(day.get("games", []))
    return games


def normalize_team_abbr(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return text


def team_abbr_from_name(value: Any) -> str:
    name = str(value or "").strip()
    return TEAM_NAME_TO_ABBR.get(name, "")


def build_template(date_label: str, games: list[dict[str, Any]]) -> list[dict[str, str]]:
    template: list[dict[str, str]] = []
    for game in games:
        away = game.get("teams", {}).get("away", {}).get("team", {})
        home = game.get("teams", {}).get("home", {}).get("team", {})
        away_abbr = normalize_team_abbr(away.get("abbreviation")) or team_abbr_from_name(away.get("name"))
        home_abbr = normalize_team_abbr(home.get("abbreviation")) or team_abbr_from_name(home.get("name"))
        if not away_abbr or not home_abbr:
            continue

        template.append({"date": date_label, "team": away_abbr, "opponent": home_abbr, **{col: "" for col in COLUMNS if col not in {"date", "team", "opponent"}}})
        template.append({"date": date_label, "team": home_abbr, "opponent": away_abbr, **{col: "" for col in COLUMNS if col not in {"date", "team", "opponent"}}})
    return template


def save_template(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a game-odds template CSV for every MLB game on a date.")
    parser.add_argument("--date", required=True, help="Game date, e.g. 2026-05-03")
    args = parser.parse_args()

    games = mlb_schedule(args.date)
    if not games:
        raise SystemExit(f"No MLB games found for {args.date}")

    template_rows = build_template(args.date, games)
    output_path = OUTPUT_DIR / f"game_odds_template_{args.date}.csv"
    save_template(output_path, template_rows)
    print(f"Wrote {len(template_rows)} template rows to {output_path}")


if __name__ == "__main__":
    main()
