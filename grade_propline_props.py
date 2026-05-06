from __future__ import annotations

"""Grade saved PropLine MLB props into ML training rows.

Usage:
    python grade_propline_props.py --date 2026-05-03

Input:
    data/odds/propline_props_YYYY-MM-DD.csv

Output:
    data/training/historical_props.csv

Supported markets:
    batter_hits
    batter_total_bases
    batter_home_runs
    pitcher_strikeouts
    pitcher_hits_allowed
    pitcher_earned_runs
"""

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"
TRAINING_DIR = DATA_DIR / "training"
MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"

SUPPORTED_MARKETS = {
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
}

TRAINING_COLUMNS = [
    "date",
    "player",
    "market",
    "line",
    "american_odds",
    "actual",
    "over",
    "team",
    "opponent",
    "book",
    "side",
    "game",
    "event_id",
]


def clean_name(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.replace("Strikeouts Thrown", "")
    text = text.replace("Hits Allowed", "")
    text = text.replace("Earned Runs", "")
    text = text.replace("Total Bases", "")
    text = text.replace("Home Runs", "")
    text = text.replace("Hits", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_name(value).lower())


def to_float(value: Any, default: float = 0.0) -> float:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").strip()))
    except ValueError:
        return default


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def mlb_schedule(date_label: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"sportId": 1, "date": date_label})
    payload = fetch_json(f"{MLB_STATS_API_BASE}/schedule?{query}")
    games: list[dict[str, Any]] = []
    for day in payload.get("dates", []):
        games.extend(day.get("games", []))
    return games


def mlb_boxscore(game_pk: int) -> dict[str, Any]:
    return fetch_json(f"{MLB_STATS_API_BASE}/game/{game_pk}/boxscore")


def team_names_from_game(game: dict[str, Any]) -> set[str]:
    teams = game.get("teams", {})
    names = set()
    for side in ("home", "away"):
        team = teams.get(side, {}).get("team", {})
        for key in ("name", "teamName", "clubName", "abbreviation"):
            if team.get(key):
                names.add(str(team[key]).lower())
    return names


def find_matching_game(prop: dict[str, Any], games: list[dict[str, Any]]) -> dict[str, Any] | None:
    event_id = str(prop.get("eventId") or prop.get("event_id") or "")
    if event_id:
        for game in games:
            if str(game.get("gamePk")) == event_id:
                return game

    home = str(prop.get("homeTeam") or prop.get("home_team") or "").lower()
    away = str(prop.get("awayTeam") or prop.get("away_team") or "").lower()
    game_text = str(prop.get("game") or "").lower()

    for game in games:
        names = team_names_from_game(game)
        joined = " ".join(names)
        if home and away and any(home in name or name in home for name in names) and any(away in name or name in away for name in names):
            return game
        if game_text and all(part.strip().lower() in joined for part in game_text.split("@") if part.strip()):
            return game
    return None


def player_stat_from_boxscore(boxscore: dict[str, Any], player_name: str, market: str) -> tuple[int | None, str, str]:
    target = normalize_name(player_name)
    if not target:
        return None, "", ""

    for side in ("home", "away"):
        team_block = boxscore.get("teams", {}).get(side, {})
        team_info = team_block.get("team", {})
        team_abbr = team_info.get("abbreviation", "")
        opponent_side = "away" if side == "home" else "home"
        opponent_info = boxscore.get("teams", {}).get(opponent_side, {}).get("team", {})
        opponent_abbr = opponent_info.get("abbreviation", "")

        for player in team_block.get("players", {}).values():
            person = player.get("person", {})
            full_name = person.get("fullName") or player.get("fullName") or ""
            if normalize_name(full_name) != target:
                continue

            if market.startswith("pitcher_"):
                pitching = player.get("stats", {}).get("pitching", {})
                if market == "pitcher_strikeouts":
                    return to_int(pitching.get("strikeOuts")), team_abbr, opponent_abbr
                if market == "pitcher_hits_allowed":
                    return to_int(pitching.get("hits")), team_abbr, opponent_abbr
                if market == "pitcher_earned_runs":
                    return to_int(pitching.get("earnedRuns")), team_abbr, opponent_abbr

            batting = player.get("stats", {}).get("batting", {})
            if market == "batter_hits":
                return to_int(batting.get("hits")), team_abbr, opponent_abbr
            if market == "batter_total_bases":
                return to_int(batting.get("totalBases")), team_abbr, opponent_abbr
            if market == "batter_home_runs":
                return to_int(batting.get("homeRuns")), team_abbr, opponent_abbr

    return None, "", ""


def load_props(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prop_date_matches(prop: dict[str, Any], date_label: str) -> bool:
    prop_date = str(prop.get("date") or prop.get("game_date") or prop.get("commence_time") or "").strip()
    return not prop_date or prop_date.startswith(date_label)


def training_row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row.get("date", "")).strip(),
        str(row.get("event_id", "")).strip(),
        str(row.get("player", "")).strip(),
        str(row.get("market", "")).strip(),
        str(row.get("line", "")).strip(),
        str(row.get("book", "")).strip(),
        str(row.get("side", "")).strip(),
    )


def append_training_rows(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str, str, str, str]] = []

    if output_path.exists():
        with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = training_row_key(row)
                if key not in merged:
                    order.append(key)
                merged[key] = row

    new_count = 0
    updated_count = 0
    for row in rows:
        key = training_row_key(row)
        normalized = {column: row.get(column, "") for column in TRAINING_COLUMNS}
        if key in merged:
            if any(str(merged[key].get(column, "")) != str(normalized.get(column, "")) for column in TRAINING_COLUMNS):
                updated_count += 1
            merged[key] = normalized
        else:
            order.append(key)
            merged[key] = normalized
            new_count += 1

    if not new_count and not updated_count:
        print("No training rows to add or update.")
        return

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRAINING_COLUMNS)
        writer.writeheader()
        for key in order:
            row = merged[key]
            writer.writerow({column: row.get(column, "") for column in TRAINING_COLUMNS})

    print(f"Upserted {new_count} new and {updated_count} updated rows into {output_path}")


def grade_props(date_label: str, input_path: Path | None = None, output_path: Path | None = None) -> dict[str, Any]:
    input_path = input_path or ODDS_DIR / f"propline_props_{date_label}.csv"
    output_path = output_path or TRAINING_DIR / "historical_props.csv"

    if not input_path.exists():
        raise FileNotFoundError(f"Could not find odds CSV: {input_path}")

    props = load_props(input_path)
    games = mlb_schedule(date_label)
    boxscores: dict[int, dict[str, Any]] = {}
    graded_rows: list[dict[str, Any]] = []
    skipped = 0

    for prop in props:
        if not prop_date_matches(prop, date_label):
            skipped += 1
            continue

        market = str(prop.get("market", "")).strip()
        side = str(prop.get("side", "")).strip().lower()
        line = prop.get("line", "")

        if market not in SUPPORTED_MARKETS or side not in {"over", "under"} or str(line).strip() == "":
            skipped += 1
            continue

        game = find_matching_game(prop, games)
        if not game:
            skipped += 1
            continue

        game_pk = int(game["gamePk"])
        if game_pk not in boxscores:
            boxscores[game_pk] = mlb_boxscore(game_pk)

        player = clean_name(prop.get("player"))
        actual, team, opponent = player_stat_from_boxscore(boxscores[game_pk], player, market)
        if actual is None:
            skipped += 1
            continue

        numeric_line = to_float(line)
        over_hit = 1 if actual > numeric_line else 0

        graded_rows.append({
            "date": date_label,
            "player": player,
            "market": market,
            "line": line,
            "american_odds": prop.get("americanOdds") or prop.get("american_odds") or "",
            "actual": actual,
            "over": over_hit,
            "team": team,
            "opponent": opponent,
            "book": prop.get("book", ""),
            "side": side.title(),
            "game": prop.get("game", ""),
            "event_id": prop.get("eventId") or prop.get("event_id") or "",
        })

    append_training_rows(graded_rows, output_path)
    return {
        "input": str(input_path),
        "output": str(output_path),
        "date": date_label,
        "propsRead": len(props),
        "rowsGraded": len(graded_rows),
        "rowsSkipped": skipped,
        "gamesFound": len(games),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade saved PropLine MLB props into ML training rows.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Game date, e.g. 2026-05-03")
    parser.add_argument("--input", default="", help="Optional odds CSV path")
    parser.add_argument("--output", default="", help="Optional training CSV output path")
    args = parser.parse_args()

    summary = grade_props(
        args.date,
        Path(args.input) if args.input else None,
        Path(args.output) if args.output else None,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
