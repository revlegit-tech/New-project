from __future__ import annotations

"""Prepare team moneyline ML training data from MLB StatsAPI game results.

This creates two rows per completed game:
- one row for the away team
- one row for the home team

Target:
    team_won = 1 if that team won, else 0

Optional odds enrichment:
    If you have game odds CSV files in data/imports, this script will try to merge:
    team_moneyline, opponent_moneyline, game_total, open/close odds, implied runs.

Examples:
    python prepare_moneyline_training.py --season 2026
    python prepare_moneyline_training.py --season 2026 --start-date 2026-03-01 --end-date 2026-05-03
    python prepare_moneyline_training.py --season 2026 --train
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


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
    "Oakland Athletics": "ATH",
    "Athletics": "ATH",
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

TEAM_ALIASES = {
    "CWS": "CHW",
    "KC": "KCR",
    "SD": "SDP",
    "SF": "SFG",
    "TB": "TBR",
    "WSH": "WSN",
    "AZ": "ARI",
    "OAK": "ATH",
}

OUTPUT_COLUMNS = [
    "date",
    "game_pk",
    "team",
    "opponent",
    "home_away",
    "team_runs",
    "opponent_runs",
    "run_diff",
    "team_won",
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


def normalize_team(value: Any) -> str:
    text = str(value or "").strip().upper()
    return TEAM_ALIASES.get(text, text[:3])


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


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


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_schedule(start_date: str, end_date: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({
        "sportId": 1,
        "startDate": start_date,
        "endDate": end_date,
        "gameType": "R",
    })
    payload = fetch_json(f"{MLB_STATS_API_BASE}/schedule?{query}")
    games: list[dict[str, Any]] = []
    for day in payload.get("dates", []):
        games.extend(day.get("games", []))
    return games


def game_is_final(game: dict[str, Any]) -> bool:
    status = game.get("status", {})
    coded = str(status.get("codedGameState", "")).upper()
    detailed = str(status.get("detailedState", "")).lower()
    return coded == "F" or "final" in detailed


def team_code(team: dict[str, Any]) -> str:
    name = str(team.get("name") or "").strip()
    if name in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[name]

    return normalize_team(
        team.get("abbreviation")
        or team.get("fileCode")
        or team.get("teamCode")
        or name
    )


def moneyline_odds_record(row: dict[str, Any]) -> dict[str, Any]:
    date = str(first_value(row, ["date", "game_date", "Date"]))[:10]
    team = normalize_team(first_value(row, ["team", "Team", "tm", "away_team", "home_team"]))
    opponent = normalize_team(first_value(row, ["opponent", "Opponent", "opp"]))

    team_ml = to_float(first_value(row, ["team_moneyline", "moneyline", "ml", "close_team_moneyline", "closing_moneyline"]))
    opponent_ml = to_float(first_value(row, ["opponent_moneyline", "opp_moneyline", "opponent_ml"]))
    game_total = to_float(first_value(row, ["game_total", "total", "close_total", "closing_total"]))

    open_team_ml = to_float(first_value(row, ["open_team_moneyline", "opening_team_moneyline", "open_moneyline"]))
    close_team_ml = to_float(first_value(row, ["close_team_moneyline", "closing_team_moneyline", "team_moneyline", "moneyline", "ml"]))
    open_total = to_float(first_value(row, ["open_game_total", "opening_total", "open_total"]))
    close_total = to_float(first_value(row, ["close_game_total", "closing_total", "game_total", "total"]))

    team_runs = to_float(first_value(row, ["team_implied_runs", "team_total", "implied_team_total"]))
    opponent_runs = to_float(first_value(row, ["opponent_implied_runs", "opponent_team_total", "opp_implied_runs"]))

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
        "team_implied_runs": team_runs,
        "opponent_implied_runs": opponent_runs,
        "opponent_implied_runs_proxy": opponent_runs,
    }


def load_game_odds_index(game_odds_dir: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}

    if not game_odds_dir.exists():
        return index

    for path in sorted(game_odds_dir.glob("*.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except Exception:
            continue

        for row in rows:
            record = moneyline_odds_record(row)
            if not record["date"] or not record["team"] or not record["opponent"]:
                continue

            index[(record["date"], record["team"], record["opponent"])] = record

            reverse = {
                **record,
                "team": record["opponent"],
                "opponent": record["team"],
                "team_moneyline": record["opponent_moneyline"],
                "opponent_moneyline": record["team_moneyline"],
                "moneyline_implied_probability": implied_probability_from_american(record["opponent_moneyline"]) if record["opponent_moneyline"] else 0.5,
                "favorite_status": favorite_status(record["opponent_moneyline"], record["team_moneyline"]),
                "team_implied_runs": record["opponent_implied_runs"],
                "opponent_implied_runs": record["team_implied_runs"],
                "opponent_implied_runs_proxy": record["team_implied_runs"],
            }
            index[(reverse["date"], reverse["team"], reverse["opponent"])] = reverse

    return index


def game_to_rows(game: dict[str, Any], odds_index: dict[tuple[str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    if not game_is_final(game):
        return []

    game_date = str(game.get("gameDate", ""))[:10]
    game_pk = str(game.get("gamePk", ""))

    teams = game.get("teams", {})
    away = teams.get("away", {})
    home = teams.get("home", {})

    away_team = away.get("team", {})
    home_team = home.get("team", {})

    away_code = team_code(away_team)
    home_code = team_code(home_team)

    away_score = away.get("score")
    home_score = home.get("score")

    if away_score is None or home_score is None or not away_code or not home_code:
        return []

    away_score = int(away_score)
    home_score = int(home_score)

    base_away = {
        "date": game_date,
        "game_pk": game_pk,
        "team": away_code,
        "opponent": home_code,
        "home_away": "away",
        "team_runs": away_score,
        "opponent_runs": home_score,
        "run_diff": away_score - home_score,
        "team_won": 1 if away_score > home_score else 0,
    }

    base_home = {
        "date": game_date,
        "game_pk": game_pk,
        "team": home_code,
        "opponent": away_code,
        "home_away": "home",
        "team_runs": home_score,
        "opponent_runs": away_score,
        "run_diff": home_score - away_score,
        "team_won": 1 if home_score > away_score else 0,
    }

    rows = []
    for base in (base_away, base_home):
        odds = odds_index.get((base["date"], base["team"], base["opponent"]), {})
        row = dict(base)
        for column in OUTPUT_COLUMNS:
            row.setdefault(column, odds.get(column, ""))
        rows.append(row)

    return rows


def prepare_moneyline_training(season: int, start_date: str, end_date: str, game_odds_dir: Path, output_path: Path) -> dict[str, Any]:
    games = fetch_schedule(start_date, end_date)
    odds_index = load_game_odds_index(game_odds_dir)

    rows: list[dict[str, Any]] = []
    for game in games:
        rows.extend(game_to_rows(game, odds_index))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})

    wins = sum(1 for row in rows if str(row.get("team_won")) == "1")
    losses = sum(1 for row in rows if str(row.get("team_won")) == "0")
    odds_matched = sum(1 for row in rows if str(row.get("team_moneyline", "")).strip())

    return {
        "season": season,
        "startDate": start_date,
        "endDate": end_date,
        "gamesFetched": len(games),
        "trainingRows": len(rows),
        "wins": wins,
        "losses": losses,
        "rowsWithOdds": odds_matched,
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare MLB team moneyline training data.")
    parser.add_argument("--season", type=int, default=datetime.now().year)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--game-odds-dir", default=str(DATA_DIR / "imports"))
    parser.add_argument("--out", default="")
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()

    start_date = args.start_date or f"{args.season}-03-01"
    end_date = args.end_date
    output_path = Path(args.out) if args.out else DATA_DIR / "training" / f"moneyline_training_{args.season}.csv"

    summary = prepare_moneyline_training(
        season=args.season,
        start_date=start_date,
        end_date=end_date,
        game_odds_dir=Path(args.game_odds_dir),
        output_path=output_path,
    )

    for key, value in summary.items():
        print(f"{key}: {value}")

    if args.train:
        print("")
        print("Training moneyline model...")
        subprocess.run([sys.executable, str(ROOT / "ml_moneyline_model.py"), "train", str(output_path)], check=True)


if __name__ == "__main__":
    main()
