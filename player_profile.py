from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATS_DIR = ROOT / "data" / "cache" / "incremental_stats"

_CSV_CACHE: dict[Path, tuple[tuple[int, int], list[dict[str, str]]]] = {}


def clean(value: Any) -> str:
    return str(value or "").strip()


def get_any(row: dict[str, Any], names: list[str]) -> str:
    lower = {clean(k).lower(): v for k, v in row.items()}
    for name in names:
        key = clean(name).lower()
        if key in lower and clean(lower[key]):
            return clean(lower[key])
    return ""


def norm(value: Any) -> str:
    text = clean(value).lower().replace(".", "").replace(",", "")
    return " ".join(text.split())


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    signature = file_signature(path)
    if signature:
        cached = _CSV_CACHE.get(path)
        if cached and cached[0] == signature:
            return cached[1]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if signature:
        _CSV_CACHE[path] = (signature, rows)
    return rows


def first_matching_player(rows: list[dict[str, str]], player: str) -> dict[str, str]:
    target = norm(player)
    for row in rows:
        if norm(row.get("player")) == target:
            return row
    for row in rows:
        if target and target in norm(row.get("player")):
            return row
    return {}


def role_for_player(season: int, player: str) -> str:
    pitchers = read_csv_rows(STATS_DIR / f"pitcher_totals_{season}.csv")
    batters = read_csv_rows(STATS_DIR / f"batter_totals_{season}.csv")

    if first_matching_player(pitchers, player):
        return "pitcher"
    if first_matching_player(batters, player):
        return "batter"
    return "batter"


def rows_for_player(path: Path, player: str) -> list[dict[str, str]]:
    target = norm(player)
    rows = []
    for row in read_csv_rows(path):
        if norm(row.get("player")) == target:
            rows.append(row)
    return rows


def latest_games(rows: list[dict[str, str]], limit: int = 10) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: clean(row.get("date")), reverse=True)[:limit]


def sum_rows(rows: list[dict[str, str]], fields: list[str]) -> dict[str, float]:
    return {field: round(sum(to_float(row.get(field)) for row in rows), 3) for field in fields}


def avg_from_sum(total: float, denom: float, digits: int = 3) -> float:
    if not denom:
        return 0.0
    return round(total / denom, digits)


def sum_any_rows(rows: list[dict[str, str]], field_map: dict[str, list[str]]) -> dict[str, float]:
    output = {}
    for output_name, names in field_map.items():
        output[output_name] = round(sum(to_float(get_any(row, names)) for row in rows), 3)
    return output


def batter_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    sums = sum_any_rows(rows, {
        "pa": ["pa", "plateAppearances", "plate_appearances"],
        "ab": ["ab", "atBats", "at_bats"],
        "runs": ["runs", "r"],
        "hits": ["hits", "h"],
        "doubles": ["doubles", "2b"],
        "triples": ["triples", "3b"],
        "homeRuns": ["homeRuns", "home_runs", "hr"],
        "rbi": ["rbi", "runsBattedIn"],
        "walks": ["walks", "baseOnBalls", "base_on_balls", "bb"],
        "strikeouts": ["strikeouts", "strikeOuts", "strike_outs", "so", "k"],
        "stolenBases": ["stolenBases", "stolen_bases", "sb"],
        "totalBases": ["totalBases", "total_bases", "tb"],
    })

    games = len(rows)
    ab = sums.get("ab", 0)
    hits = sums.get("hits", 0)
    total_bases = sums.get("totalBases", 0)

    return {
        **sums,
        "games": games,
        "avg": avg_from_sum(hits, ab, 3),
        "slg": avg_from_sum(total_bases, ab, 3),
        "hitsPerGame": avg_from_sum(hits, games, 3),
        "totalBasesPerGame": avg_from_sum(total_bases, games, 3),
        "homeRunsPerGame": avg_from_sum(sums.get("homeRuns", 0), games, 3),
        "strikeoutsPerGame": avg_from_sum(sums.get("strikeouts", 0), games, 3),
        "walksPerGame": avg_from_sum(sums.get("walks", 0), games, 3),
    }

def pitcher_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    sums = sum_any_rows(rows, {
        "inningsPitched": ["inningsPitched", "ip"],
        "strikeOuts": ["strikeOuts", "strikeouts", "strike_outs", "so", "k"],
        "hits": ["hits", "h"],
        "earnedRuns": ["earnedRuns", "earned_runs", "er"],
        "walks": ["walks", "baseOnBalls", "base_on_balls", "bb"],
        "homeRuns": ["homeRuns", "home_runs", "hr"],
        "runs": ["runs", "r"],
        "battersFaced": ["battersFaced", "batters_faced", "bf"],
        "pitches": ["pitches", "pitchesThrown", "pitches_thrown"],
    })

    games = len(rows)
    ip = sums.get("inningsPitched", 0)
    er = sums.get("earnedRuns", 0)

    return {
        **sums,
        "games": games,
        "strikeoutsPerGame": avg_from_sum(sums.get("strikeOuts", 0), games, 3),
        "hitsAllowedPerGame": avg_from_sum(sums.get("hits", 0), games, 3),
        "earnedRunsPerGame": avg_from_sum(er, games, 3),
        "walksPerGame": avg_from_sum(sums.get("walks", 0), games, 3),
        "eraEstimate": round((er * 9 / ip), 3) if ip else 0.0,
    }

def clean_game_log_row(row: dict[str, str], role: str) -> dict[str, Any]:
    if role == "pitcher":
        return {
            "date": clean(row.get("date")),
            "team": clean(row.get("team")),
            "opponent": clean(row.get("opponent")),
            "inningsPitched": get_any(row, ["inningsPitched", "ip"]),
            "strikeOuts": get_any(row, ["strikeOuts", "strikeouts", "strike_outs", "so", "k"]),
            "hits": get_any(row, ["hits", "h"]),
            "earnedRuns": get_any(row, ["earnedRuns", "earned_runs", "er"]),
            "walks": get_any(row, ["walks", "baseOnBalls", "base_on_balls", "bb"]),
            "homeRuns": get_any(row, ["homeRuns", "home_runs", "hr"]),
            "pitches": get_any(row, ["pitches", "pitchesThrown", "pitches_thrown"]),
        }

    return {
        "date": clean(row.get("date")),
        "team": clean(row.get("team")),
        "opponent": clean(row.get("opponent")),
        "ab": get_any(row, ["ab", "atBats", "at_bats"]),
        "hits": get_any(row, ["hits", "h"]),
        "totalBases": get_any(row, ["totalBases", "total_bases", "tb"]),
        "homeRuns": get_any(row, ["homeRuns", "home_runs", "hr"]),
        "rbi": get_any(row, ["rbi", "runsBattedIn"]),
        "walks": get_any(row, ["walks", "baseOnBalls", "base_on_balls", "bb"]),
        "strikeouts": get_any(row, ["strikeouts", "strikeOuts", "strike_outs", "so", "k"]),
        "runs": get_any(row, ["runs", "r"]),
    }




def over_count(rows: list[dict[str, str]], field_names: list[str], line: float) -> int:
    count = 0
    for row in rows:
        value = to_float(get_any(row, field_names))
        if value > line:
            count += 1
    return count


def batter_prop_trends(rows: list[dict[str, str]]) -> dict[str, Any]:
    last5 = latest_games(rows, 5)
    last10 = latest_games(rows, 10)

    return {
        "last5": {
            "hitGames": over_count(last5, ["hits", "h"], 0.5),
            "totalBasesOver1_5": over_count(last5, ["totalBases", "total_bases", "tb"], 1.5),
            "homeRunGames": over_count(last5, ["homeRuns", "home_runs", "hr"], 0.5),
            "walkGames": over_count(last5, ["walks", "baseOnBalls", "base_on_balls", "bb"], 0.5),
            "strikeoutGames": over_count(last5, ["strikeouts", "strikeOuts", "strike_outs", "so", "k"], 0.5),
            "games": len(last5),
        },
        "last10": {
            "hitGames": over_count(last10, ["hits", "h"], 0.5),
            "totalBasesOver1_5": over_count(last10, ["totalBases", "total_bases", "tb"], 1.5),
            "homeRunGames": over_count(last10, ["homeRuns", "home_runs", "hr"], 0.5),
            "walkGames": over_count(last10, ["walks", "baseOnBalls", "base_on_balls", "bb"], 0.5),
            "strikeoutGames": over_count(last10, ["strikeouts", "strikeOuts", "strike_outs", "so", "k"], 0.5),
            "games": len(last10),
        },
    }


def pitcher_prop_trends(rows: list[dict[str, str]]) -> dict[str, Any]:
    last5 = latest_games(rows, 5)
    last10 = latest_games(rows, 10)

    return {
        "last5": {
            "strikeoutsOver4_5": over_count(last5, ["strikeOuts", "strikeouts", "strike_outs", "so", "k"], 4.5),
            "strikeoutsOver5_5": over_count(last5, ["strikeOuts", "strikeouts", "strike_outs", "so", "k"], 5.5),
            "hitsAllowedOver4_5": over_count(last5, ["hits", "h"], 4.5),
            "earnedRunsOver2_5": over_count(last5, ["earnedRuns", "earned_runs", "er"], 2.5),
            "games": len(last5),
        },
        "last10": {
            "strikeoutsOver4_5": over_count(last10, ["strikeOuts", "strikeouts", "strike_outs", "so", "k"], 4.5),
            "strikeoutsOver5_5": over_count(last10, ["strikeOuts", "strikeouts", "strike_outs", "so", "k"], 5.5),
            "hitsAllowedOver4_5": over_count(last10, ["hits", "h"], 4.5),
            "earnedRunsOver2_5": over_count(last10, ["earnedRuns", "earned_runs", "er"], 2.5),
            "games": len(last10),
        },
    }

def get_profile(season: int, date_label: str, player: str) -> dict[str, Any]:
    role = role_for_player(season, player)

    if role == "pitcher":
        totals_path = STATS_DIR / f"pitcher_totals_{season}.csv"
        logs_path = STATS_DIR / f"pitcher_game_logs_{season}.csv"
    else:
        totals_path = STATS_DIR / f"batter_totals_{season}.csv"
        logs_path = STATS_DIR / f"batter_game_logs_{season}.csv"

    totals = first_matching_player(read_csv_rows(totals_path), player)
    logs_all = rows_for_player(logs_path, totals.get("player") or player)
    logs_latest = latest_games(logs_all, 10)

    last5_rows = latest_games(logs_all, 5)
    last10_rows = latest_games(logs_all, 10)

    if role == "pitcher":
        season_summary = pitcher_summary(logs_all)
        last5 = pitcher_summary(last5_rows)
        last10 = pitcher_summary(last10_rows)
        prop_trends = pitcher_prop_trends(logs_all)
    else:
        season_summary = batter_summary(logs_all)
        last5 = batter_summary(last5_rows)
        last10 = batter_summary(last10_rows)
        prop_trends = batter_prop_trends(logs_all)

    # Autofill game context.
    game_context = {}
    try:
        from player_autofill import autofill_player
        game_context = autofill_player(season, date_label, totals.get("player") or player, role)
    except Exception as error:
        game_context = {"error": str(error)}

    # Savant is optional.
    savant = {}
    opposing_pitcher_savant = {}

    try:
        if role == "pitcher":
            from savant_features import lookup_pitcher

            savant = lookup_pitcher(totals.get("player") or player, season)
        else:
            from savant_features import lookup_batter, lookup_pitcher

            savant = lookup_batter(totals.get("player") or player, season)

            opposing_pitcher = (
                game_context.get("pitcher")
                or game_context.get("opposingPitcher")
                or ""
            )
            if opposing_pitcher:
                opposing_pitcher_savant = lookup_pitcher(opposing_pitcher, season)
    except Exception:
        savant = savant or {}
        opposing_pitcher_savant = opposing_pitcher_savant or {}

    return {
        "season": season,
        "date": date_label,
        "player": totals.get("player") or player,
        "role": role,
        "team": totals.get("team") or game_context.get("team", ""),
        "totals": totals,
        "gameContext": game_context,
        "recent": {
            "last5": last5,
            "last10": last10,
            "season": season_summary,
            "propTrends": prop_trends,
        },
        "gameLogs": [clean_game_log_row(row, role) for row in logs_latest],
        "savant": savant,
        "opposingPitcherSavant": opposing_pitcher_savant,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Player profile endpoint helper.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--date", required=True)
    parser.add_argument("--player", required=True)
    args = parser.parse_args()

    print(json.dumps(get_profile(args.season, args.date, args.player), indent=2))


if __name__ == "__main__":
    main()
