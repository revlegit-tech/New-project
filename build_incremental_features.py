from __future__ import annotations

"""Build aggregate feature files from incremental MLB game logs.

Reads:
- data/cache/incremental_stats/batter_game_logs_YEAR.csv
- data/cache/incremental_stats/pitcher_game_logs_YEAR.csv
- data/cache/incremental_stats/team_game_logs_YEAR.csv
- data/cache/incremental_stats/batter_vs_pitcher_pa_YEAR.csv

Writes:
- batter_totals_YEAR.csv
- pitcher_totals_YEAR.csv
- team_totals_YEAR.csv
- bvp_totals_YEAR.csv
- batter_recent_YEAR.csv
- pitcher_recent_YEAR.csv
- bullpen_recent_YEAR.csv
- feature_status_YEAR.json

Also supports MLB StatsAPI cross-reference for selected players.

Default behavior:
- regular season only
- 2026 regular season starts 2026-03-25
"""

import argparse
import csv
import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from batter_recent_vs_hand_features import build_batter_recent_vs_hand

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache" / "incremental_stats"
MLB_BASE = "https://statsapi.mlb.com/api/v1"

REGULAR_SEASON_START_DATES = {
    2024: "2024-03-20",
    2025: "2025-03-18",
    2026: "2026-03-25",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


# Returns 0.0 for missing values. Appropriate for stat aggregation.
# For ML feature extraction use ml_prop_model.to_float() instead.
def to_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric text to float, returning default for missing/invalid values.
    
    This helper is for aggregation/reporting where default=0.0 is intentional.
    Do not use it for ML feature extraction when missingness must stay explicit;
    use ml_prop_model.to_float() or a nullable parser instead.
    """
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def safe_div(numerator: float, denominator: float, digits: int = 3) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator, digits)


def days_between(date_a: str, date_b: str) -> int:
    try:
        d_a = datetime.strptime(clean(date_a)[:10], "%Y-%m-%d")
        d_b = datetime.strptime(clean(date_b)[:10], "%Y-%m-%d")
        return abs((d_b - d_a).days)
    except ValueError:
        return -1


def platoon_matchup(throws: str, bats: str) -> str:
    t = clean(throws).upper()[:1]
    b = clean(bats).upper()[:1]
    if b == "S":
        return "switch_hitter"
    if t and b and t == b:
        return "same_side"
    if t and b and t != b:
        return "opposite_side"
    return "unknown"


def rate(numerator: float, denominator: float, digits: int = 4) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator, digits)


def pct(numerator: float, denominator: float, digits: int = 2) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, digits)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def row_phase(row: dict[str, Any], season: int) -> str:
    explicit = clean(row.get("seasonPhase"))
    if explicit:
        return explicit

    date_label = clean(row.get("date"))
    regular_start = REGULAR_SEASON_START_DATES.get(season, f"{season}-03-25")
    return "regular" if date_label >= regular_start else "practice"


def filter_phase(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, str]]:
    phase = clean(phase).lower() or "regular"
    if phase in {"all", "any"}:
        return rows
    return [row for row in rows if row_phase(row, season) == phase]


def parse_ip(value: Any) -> float:
    """Parse baseball innings correctly.

    5.1 = 5 + 1/3
    5.2 = 5 + 2/3
    """
    text = clean(value)
    if not text:
        return 0.0

    if "." not in text:
        return to_float(text)

    whole, frac = text.split(".", 1)
    innings = to_float(whole)

    if frac == "1":
        return innings + (1 / 3)
    if frac == "2":
        return innings + (2 / 3)

    # Fallback for already-decimal inputs.
    return to_float(text)


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def mlb_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return fetch_json(f"{MLB_BASE}/{endpoint}?{query}")


def file_paths(season: int) -> dict[str, Path]:
    return {
        "batters": CACHE_DIR / f"batter_game_logs_{season}.csv",
        "pitchers": CACHE_DIR / f"pitcher_game_logs_{season}.csv",
        "teams": CACHE_DIR / f"team_game_logs_{season}.csv",
        "bvp": CACHE_DIR / f"batter_vs_pitcher_pa_{season}.csv",
        "batterTotals": CACHE_DIR / f"batter_totals_{season}.csv",
        "pitcherTotals": CACHE_DIR / f"pitcher_totals_{season}.csv",
        "teamTotals": CACHE_DIR / f"team_totals_{season}.csv",
        "bvpTotals": CACHE_DIR / f"bvp_totals_{season}.csv",
        "batterRecent": CACHE_DIR / f"batter_recent_{season}.csv",
        "batterRecentVsHand": CACHE_DIR / f"batter_recent_vs_hand_{season}.csv",
        "pitcherRecent": CACHE_DIR / f"pitcher_recent_{season}.csv",
        "bullpenRecent": CACHE_DIR / f"bullpen_recent_{season}.csv",
        "status": CACHE_DIR / f"feature_status_{season}.json",
    }


BATTER_TOTAL_FIELDS = [
    "season", "seasonPhase", "playerId", "player", "team", "games",
    "pa", "ab", "runs", "hits", "doubles", "triples", "homeRuns", "rbi",
    "walks", "strikeouts", "stolenBases", "totalBases",
    "avg", "obp_est", "slg", "ops_est",
    "hitsPerGame", "totalBasesPerGame", "homeRunsPerGame",
    "runsPerGame", "rbiPerGame", "strikeoutsPerGame", "walksPerGame",
    "kRate", "bbRate", "babip", "avgHome", "avgAway",
]

PITCHER_TOTAL_FIELDS = [
    "season", "seasonPhase", "playerId", "player", "team", "games",
    "ip", "runs", "earnedRuns", "hitsAllowed", "homeRunsAllowed",
    "walks", "strikeouts", "battersFaced", "pitchesThrown", "strikes",
    "era", "whip", "kPer9", "bbPer9", "hrPer9",
    "strikeoutsPerGame", "hitsAllowedPerGame", "earnedRunsPerGame",
    "walksPerGame", "homeRunsAllowedPerGame", "kRate", "bbRate", "babip",
]

TEAM_TOTAL_FIELDS = [
    "season", "seasonPhase", "team", "teamName", "games",
    "runs", "hits", "homeRuns", "strikeouts", "walks", "atBats", "totalBases",
    "runsPerGame", "hitsPerGame", "homeRunsPerGame", "strikeoutsPerGame", "walksPerGame",
    "runsAllowed", "hitsAllowed", "pitchingStrikeouts", "pitchingWalks", "pitchingHomeRuns",
    "runsAllowedPerGame", "hitsAllowedPerGame", "pitchingStrikeoutsPerGame",
    "pitchingWalksPerGame", "pitchingHomeRunsPerGame",
]

BVP_TOTAL_FIELDS = [
    "season", "seasonPhase", "batterId", "batter", "pitcherId", "pitcher",
    "plateAppearances", "atBats", "hits", "homeRuns", "walks", "strikeouts",
    "totalBases", "avg", "slg", "kRate", "bbRate",
]

BATTER_RECENT_FIELDS = [
    "season", "seasonPhase", "playerId", "player", "team", "games",
    "last5HitsPerGame", "last10HitsPerGame", "last15HitsPerGame",
    "last5TotalBasesPerGame", "last10TotalBasesPerGame", "last15TotalBasesPerGame",
    "last5HomeRunsPerGame", "last10HomeRunsPerGame", "last15HomeRunsPerGame",
    "last5StrikeoutsPerGame", "last10StrikeoutsPerGame", "last15StrikeoutsPerGame",
    "daysRest",
]

BATTER_RECENT_VS_HAND_FIELDS = [
    "season", "seasonPhase", "date", "playerId", "player", "team", "windowDays",
    "batter_recent_hits_vs_lhp", "batter_recent_hits_vs_rhp",
    "batter_recent_avg_vs_lhp", "batter_recent_avg_vs_rhp",
    "batter_recent_pa_vs_lhp", "batter_recent_pa_vs_rhp",
    "batter_recent_ab_vs_lhp", "batter_recent_ab_vs_rhp",
    "batter_recent_games_vs_lhp", "batter_recent_games_vs_rhp",
]

PITCHER_RECENT_FIELDS = [
    "season", "seasonPhase", "playerId", "player", "team", "games",
    "last5StrikeoutsPerGame", "last10StrikeoutsPerGame", "last15StrikeoutsPerGame",
    "last5HitsAllowedPerGame", "last10HitsAllowedPerGame", "last15HitsAllowedPerGame",
    "last5EarnedRunsPerGame", "last10EarnedRunsPerGame", "last15EarnedRunsPerGame",
    "last5WalksPerGame", "last10WalksPerGame", "last15WalksPerGame",
    "daysRest",
]

BULLPEN_RECENT_FIELDS = [
    "season", "seasonPhase", "date", "team",
    "bullpen_ip_7d", "bullpen_er_7d", "bullpen_runs_7d",
    "bullpen_hits_7d", "bullpen_walks_7d", "bullpen_strikeouts_7d",
    "bullpen_appearances_7d", "bullpen_era_7d",
]


def build_batter_totals(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        key = (clean(row.get("playerId")), clean(row.get("player")))
        if not key[1]:
            continue

        item = grouped.setdefault(key, {
            "season": season,
            "seasonPhase": phase,
            "playerId": key[0],
            "player": key[1],
            "team": clean(row.get("team")),
            "games": 0,
            "pa": 0.0,
            "ab": 0.0,
            "runs": 0.0,
            "hits": 0.0,
            "doubles": 0.0,
            "triples": 0.0,
            "homeRuns": 0.0,
            "rbi": 0.0,
            "walks": 0.0,
            "strikeouts": 0.0,
            "stolenBases": 0.0,
            "totalBases": 0.0,
            "homeHits": 0.0,
            "homeAb": 0.0,
            "awayHits": 0.0,
            "awayAb": 0.0,
        })

        item["games"] += 1
        item["team"] = clean(row.get("team")) or item["team"]
        item["pa"] += to_float(row.get("plateAppearances"))
        item["ab"] += to_float(row.get("atBats"))
        item["runs"] += to_float(row.get("runs"))
        item["hits"] += to_float(row.get("hits"))
        item["doubles"] += to_float(row.get("doubles"))
        item["triples"] += to_float(row.get("triples"))
        item["homeRuns"] += to_float(row.get("homeRuns"))
        item["rbi"] += to_float(row.get("rbi"))
        item["walks"] += to_float(row.get("baseOnBalls"))
        item["strikeouts"] += to_float(row.get("strikeOuts"))
        item["stolenBases"] += to_float(row.get("stolenBases"))
        item["totalBases"] += to_float(row.get("totalBases"))
        side = clean(row.get("side")).lower()
        if side == "home":
            item["homeHits"] += to_float(row.get("hits"))
            item["homeAb"] += to_float(row.get("atBats"))
        elif side == "away":
            item["awayHits"] += to_float(row.get("hits"))
            item["awayAb"] += to_float(row.get("atBats"))

    output = []
    for item in grouped.values():
        games = item["games"]
        ab = item["ab"]
        pa = item["pa"]
        hits = item["hits"]
        walks = item["walks"]
        tb = item["totalBases"]

        # OBP is estimated because HBP/SF may not be present in this saved boxscore schema.
        obp_denominator = ab + walks

        item.update({
            "avg": safe_div(hits, ab, 3),
            "obp_est": safe_div(hits + walks, obp_denominator, 3),
            "slg": safe_div(tb, ab, 3),
            "ops_est": round(safe_div(hits + walks, obp_denominator, 3) + safe_div(tb, ab, 3), 3),
            "hitsPerGame": safe_div(hits, games, 3),
            "totalBasesPerGame": safe_div(tb, games, 3),
            "homeRunsPerGame": safe_div(item["homeRuns"], games, 3),
            "runsPerGame": safe_div(item["runs"], games, 3),
            "rbiPerGame": safe_div(item["rbi"], games, 3),
            "strikeoutsPerGame": safe_div(item["strikeouts"], games, 3),
            "walksPerGame": safe_div(item["walks"], games, 3),
            "kRate": pct(item["strikeouts"], pa, 2),
            "bbRate": pct(item["walks"], pa, 2),
            "babip": safe_div(item["hits"] - item["homeRuns"], item["ab"] - item["strikeouts"] - item["homeRuns"], 3),
            "avgHome": safe_div(item["homeHits"], item["homeAb"], 3),
            "avgAway": safe_div(item["awayHits"], item["awayAb"], 3),
        })
        output.append(item)

    return sorted(output, key=lambda x: (-to_float(x.get("games")), clean(x.get("player")).lower()))


def build_pitcher_totals(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        key = (clean(row.get("playerId")), clean(row.get("player")))
        if not key[1]:
            continue

        item = grouped.setdefault(key, {
            "season": season,
            "seasonPhase": phase,
            "playerId": key[0],
            "player": key[1],
            "team": clean(row.get("team")),
            "games": 0,
            "ip": 0.0,
            "runs": 0.0,
            "earnedRuns": 0.0,
            "hitsAllowed": 0.0,
            "homeRunsAllowed": 0.0,
            "walks": 0.0,
            "strikeouts": 0.0,
            "battersFaced": 0.0,
            "pitchesThrown": 0.0,
            "strikes": 0.0,
        })

        item["games"] += 1
        item["team"] = clean(row.get("team")) or item["team"]
        item["ip"] += parse_ip(row.get("inningsPitched"))
        item["runs"] += to_float(row.get("runs"))
        item["earnedRuns"] += to_float(row.get("earnedRuns"))
        item["hitsAllowed"] += to_float(row.get("hits"))
        item["homeRunsAllowed"] += to_float(row.get("homeRuns"))
        item["walks"] += to_float(row.get("baseOnBalls"))
        item["strikeouts"] += to_float(row.get("strikeOuts"))
        item["battersFaced"] += to_float(row.get("battersFaced"))
        item["pitchesThrown"] += to_float(row.get("pitchesThrown"))
        item["strikes"] += to_float(row.get("strikes"))

    output = []
    for item in grouped.values():
        games = item["games"]
        ip = item["ip"]
        bf = item["battersFaced"]

        item.update({
            "ip": round(ip, 3),
            "era": safe_div(item["earnedRuns"] * 9, ip, 2),
            "whip": safe_div(item["walks"] + item["hitsAllowed"], ip, 3),
            "kPer9": safe_div(item["strikeouts"] * 9, ip, 2),
            "bbPer9": safe_div(item["walks"] * 9, ip, 2),
            "hrPer9": safe_div(item["homeRunsAllowed"] * 9, ip, 2),
            "strikeoutsPerGame": safe_div(item["strikeouts"], games, 3),
            "hitsAllowedPerGame": safe_div(item["hitsAllowed"], games, 3),
            "earnedRunsPerGame": safe_div(item["earnedRuns"], games, 3),
            "walksPerGame": safe_div(item["walks"], games, 3),
            "homeRunsAllowedPerGame": safe_div(item["homeRunsAllowed"], games, 3),
            "kRate": pct(item["strikeouts"], bf, 2),
            "bbRate": pct(item["walks"], bf, 2),
            "babip": safe_div(item["hitsAllowed"] - item["homeRunsAllowed"], bf - item["strikeouts"] - item["homeRunsAllowed"], 3),
        })
        output.append(item)

    return sorted(output, key=lambda x: (-to_float(x.get("ip")), clean(x.get("player")).lower()))


def build_team_totals(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for row in rows:
        team = clean(row.get("team")).upper()
        if not team:
            continue

        item = grouped.setdefault(team, {
            "season": season,
            "seasonPhase": phase,
            "team": team,
            "teamName": clean(row.get("teamName")),
            "games": 0,
            "runs": 0.0,
            "hits": 0.0,
            "homeRuns": 0.0,
            "strikeouts": 0.0,
            "walks": 0.0,
            "atBats": 0.0,
            "totalBases": 0.0,
            "runsAllowed": 0.0,
            "hitsAllowed": 0.0,
            "pitchingStrikeouts": 0.0,
            "pitchingWalks": 0.0,
            "pitchingHomeRuns": 0.0,
        })

        item["games"] += 1
        item["teamName"] = clean(row.get("teamName")) or item["teamName"]
        item["runs"] += to_float(row.get("runs"))
        item["hits"] += to_float(row.get("hits"))
        item["homeRuns"] += to_float(row.get("homeRuns"))
        item["strikeouts"] += to_float(row.get("strikeOuts"))
        item["walks"] += to_float(row.get("baseOnBalls"))
        item["atBats"] += to_float(row.get("atBats"))
        item["totalBases"] += to_float(row.get("totalBases"))
        item["runsAllowed"] += to_float(row.get("pitchingRuns"))
        item["hitsAllowed"] += to_float(row.get("pitchingHits"))
        item["pitchingStrikeouts"] += to_float(row.get("pitchingStrikeOuts"))
        item["pitchingWalks"] += to_float(row.get("pitchingBaseOnBalls"))
        item["pitchingHomeRuns"] += to_float(row.get("pitchingHomeRuns"))

    output = []
    for item in grouped.values():
        games = item["games"]
        item.update({
            "runsPerGame": safe_div(item["runs"], games, 3),
            "hitsPerGame": safe_div(item["hits"], games, 3),
            "homeRunsPerGame": safe_div(item["homeRuns"], games, 3),
            "strikeoutsPerGame": safe_div(item["strikeouts"], games, 3),
            "walksPerGame": safe_div(item["walks"], games, 3),
            "runsAllowedPerGame": safe_div(item["runsAllowed"], games, 3),
            "hitsAllowedPerGame": safe_div(item["hitsAllowed"], games, 3),
            "pitchingStrikeoutsPerGame": safe_div(item["pitchingStrikeouts"], games, 3),
            "pitchingWalksPerGame": safe_div(item["pitchingWalks"], games, 3),
            "pitchingHomeRunsPerGame": safe_div(item["pitchingHomeRuns"], games, 3),
        })
        output.append(item)

    return sorted(output, key=lambda x: clean(x.get("team")))


def build_bvp_totals(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        key = (clean(row.get("batterId")), clean(row.get("pitcherId")))
        if not key[0] or not key[1]:
            continue

        item = grouped.setdefault(key, {
            "season": season,
            "seasonPhase": phase,
            "batterId": key[0],
            "batter": clean(row.get("batter")),
            "pitcherId": key[1],
            "pitcher": clean(row.get("pitcher")),
            "plateAppearances": 0.0,
            "atBats": 0.0,
            "hits": 0.0,
            "homeRuns": 0.0,
            "walks": 0.0,
            "strikeouts": 0.0,
            "totalBases": 0.0,
        })

        item["plateAppearances"] += 1
        item["atBats"] += to_float(row.get("isAtBat"))
        item["hits"] += to_float(row.get("hit"))
        item["homeRuns"] += to_float(row.get("homeRun"))
        item["walks"] += to_float(row.get("walk"))
        item["strikeouts"] += to_float(row.get("strikeout"))
        item["totalBases"] += to_float(row.get("totalBases"))

    output = []
    for item in grouped.values():
        ab = item["atBats"]
        pa = item["plateAppearances"]
        item.update({
            "avg": safe_div(item["hits"], ab, 3),
            "slg": safe_div(item["totalBases"], ab, 3),
            "kRate": pct(item["strikeouts"], pa, 2),
            "bbRate": pct(item["walks"], pa, 2),
        })
        output.append(item)

    return sorted(output, key=lambda x: -to_float(x.get("plateAppearances")))


def recent_average(rows: list[dict[str, str]], key: str, n: int) -> float:
    values = [
        value
        for row in rows[-n:]
        if not math.isnan(value := to_float(row.get(key), math.nan))
    ]
    return safe_div(sum(values), len(values), 3) if values else 0.0


def build_batter_recent(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for row in sorted(rows, key=lambda x: clean(x.get("date"))):
        key = (clean(row.get("playerId")), clean(row.get("player")))
        if key[1]:
            grouped[key].append(row)

    output = []
    for (player_id, player), items in grouped.items():
        team = clean(items[-1].get("team"))
        last_two_dates = [clean(r.get("date")) for r in items[-2:]]
        days_rest = days_between(last_two_dates[0], last_two_dates[1]) if len(last_two_dates) == 2 else -1
        output.append({
            "season": season,
            "seasonPhase": phase,
            "playerId": player_id,
            "player": player,
            "team": team,
            "games": len(items),
            "last5HitsPerGame": recent_average(items, "hits", 5),
            "last10HitsPerGame": recent_average(items, "hits", 10),
            "last15HitsPerGame": recent_average(items, "hits", 15),
            "last5TotalBasesPerGame": recent_average(items, "totalBases", 5),
            "last10TotalBasesPerGame": recent_average(items, "totalBases", 10),
            "last15TotalBasesPerGame": recent_average(items, "totalBases", 15),
            "last5HomeRunsPerGame": recent_average(items, "homeRuns", 5),
            "last10HomeRunsPerGame": recent_average(items, "homeRuns", 10),
            "last15HomeRunsPerGame": recent_average(items, "homeRuns", 15),
            "last5StrikeoutsPerGame": recent_average(items, "strikeOuts", 5),
            "last10StrikeoutsPerGame": recent_average(items, "strikeOuts", 10),
            "last15StrikeoutsPerGame": recent_average(items, "strikeOuts", 15),
            "daysRest": days_rest,
        })

    return sorted(output, key=lambda x: (-to_float(x.get("games")), clean(x.get("player")).lower()))


def build_pitcher_recent(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for row in sorted(rows, key=lambda x: clean(x.get("date"))):
        key = (clean(row.get("playerId")), clean(row.get("player")))
        if key[1]:
            grouped[key].append(row)

    output = []
    for (player_id, player), items in grouped.items():
        team = clean(items[-1].get("team"))
        last_two_dates = [clean(r.get("date")) for r in items[-2:]]
        days_rest = days_between(last_two_dates[0], last_two_dates[1]) if len(last_two_dates) == 2 else -1
        output.append({
            "season": season,
            "seasonPhase": phase,
            "playerId": player_id,
            "player": player,
            "team": team,
            "games": len(items),
            "last5StrikeoutsPerGame": recent_average(items, "strikeOuts", 5),
            "last10StrikeoutsPerGame": recent_average(items, "strikeOuts", 10),
            "last15StrikeoutsPerGame": recent_average(items, "strikeOuts", 15),
            "last5HitsAllowedPerGame": recent_average(items, "hits", 5),
            "last10HitsAllowedPerGame": recent_average(items, "hits", 10),
            "last15HitsAllowedPerGame": recent_average(items, "hits", 15),
            "last5EarnedRunsPerGame": recent_average(items, "earnedRuns", 5),
            "last10EarnedRunsPerGame": recent_average(items, "earnedRuns", 10),
            "last15EarnedRunsPerGame": recent_average(items, "earnedRuns", 15),
            "last5WalksPerGame": recent_average(items, "baseOnBalls", 5),
            "last10WalksPerGame": recent_average(items, "baseOnBalls", 10),
            "last15WalksPerGame": recent_average(items, "baseOnBalls", 15),
            "daysRest": days_rest,
        })

    return sorted(output, key=lambda x: (-to_float(x.get("games")), clean(x.get("player")).lower()))


def parse_date_label(value: Any) -> datetime | None:
    try:
        return datetime.strptime(clean(value)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def is_relief_appearance(row: dict[str, str], starter_ids: set[tuple[str, str, str]]) -> bool:
    """Return True when a pitcher row is not the likely starter for that team/game.

    The current pitcher game-log cache does not store batting order/entry inning,
    so we approximate the starter as the pitcher with the most innings pitched for
    each team/game. This excludes the starter and keeps the bullpen appearances.
    """
    key = (clean(row.get("gamePk")), clean(row.get("team")).upper(), clean(row.get("playerId")))
    return key not in starter_ids


def likely_starter_ids(pitcher_rows: list[dict[str, str]]) -> set[tuple[str, str, str]]:
    starters: set[tuple[str, str, str]] = set()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for row in pitcher_rows:
        game_pk = clean(row.get("gamePk"))
        team = clean(row.get("team")).upper()
        if game_pk and team:
            grouped[(game_pk, team)].append(row)

    for (game_pk, team), rows in grouped.items():
        starter = max(
            rows,
            key=lambda row: (
                parse_ip(row.get("inningsPitched")),
                to_float(row.get("battersFaced")),
                to_float(row.get("pitchesThrown")),
            ),
        )
        player_id = clean(starter.get("playerId"))
        if player_id:
            starters.add((game_pk, team, player_id))

    return starters


def build_bullpen_recent(rows: list[dict[str, str]], season: int, phase: str) -> list[dict[str, Any]]:
    """Build rolling 7-day bullpen ERA by team from pitcher game logs.

    Each output row is keyed by team/date and uses only relief appearances from
    the seven days before that date, so it is safe to join as a pregame feature.
    """
    starter_ids = likely_starter_ids(rows)
    relief_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        if not is_relief_appearance(row, starter_ids):
            continue

        team = clean(row.get("team")).upper()
        date_value = parse_date_label(row.get("date"))
        if not team or date_value is None:
            continue

        relief_by_team[team].append({
            "date": date_value,
            "ip": parse_ip(row.get("inningsPitched")),
            "er": to_float(row.get("earnedRuns")),
            "runs": to_float(row.get("runs")),
            "hits": to_float(row.get("hits")),
            "walks": to_float(row.get("baseOnBalls")),
            "strikeouts": to_float(row.get("strikeOuts")),
        })

    for team_rows in relief_by_team.values():
        team_rows.sort(key=lambda item: item["date"])

    dates_by_team: dict[str, list[datetime]] = defaultdict(list)
    for row in rows:
        team = clean(row.get("team")).upper()
        date_value = parse_date_label(row.get("date"))
        if team and date_value is not None:
            dates_by_team[team].append(date_value)

    output: list[dict[str, Any]] = []

    for team, date_values in sorted(dates_by_team.items()):
        unique_dates = sorted(set(date_values))
        relief_rows = relief_by_team.get(team, [])
        window: deque[dict[str, Any]] = deque()
        idx = 0
        totals = {"ip": 0.0, "er": 0.0, "runs": 0.0, "hits": 0.0, "walks": 0.0, "strikeouts": 0.0}

        for current_date in unique_dates:
            while idx < len(relief_rows) and relief_rows[idx]["date"] < current_date:
                item = relief_rows[idx]
                window.append(item)
                for key in totals:
                    totals[key] += item[key]
                idx += 1

            window_start = current_date - timedelta(days=7)
            while window and window[0]["date"] < window_start:
                item = window.popleft()
                for key in totals:
                    totals[key] -= item[key]

            ip = totals["ip"]
            earned_runs = totals["er"]

            output.append({
                "season": season,
                "seasonPhase": phase,
                "date": current_date.strftime("%Y-%m-%d"),
                "team": team,
                "bullpen_ip_7d": round(ip, 3),
                "bullpen_er_7d": round(earned_runs, 3),
                "bullpen_runs_7d": round(totals["runs"], 3),
                "bullpen_hits_7d": round(totals["hits"], 3),
                "bullpen_walks_7d": round(totals["walks"], 3),
                "bullpen_strikeouts_7d": round(totals["strikeouts"], 3),
                "bullpen_appearances_7d": len(window),
                "bullpen_era_7d": round((earned_runs * 9) / ip, 3) if ip else "",
            })

    return output


def build_features(season: int = 2026, phase: str = "regular") -> dict[str, Any]:
    paths = file_paths(season)

    batter_rows = filter_phase(read_csv_rows(paths["batters"]), season, phase)
    pitcher_rows = filter_phase(read_csv_rows(paths["pitchers"]), season, phase)
    team_rows = filter_phase(read_csv_rows(paths["teams"]), season, phase)
    bvp_rows = filter_phase(read_csv_rows(paths["bvp"]), season, phase)

    batter_totals = build_batter_totals(batter_rows, season, phase)
    pitcher_totals = build_pitcher_totals(pitcher_rows, season, phase)
    team_totals = build_team_totals(team_rows, season, phase)
    bvp_totals = build_bvp_totals(bvp_rows, season, phase)
    batter_recent = build_batter_recent(batter_rows, season, phase)
    batter_recent_vs_hand = build_batter_recent_vs_hand(batter_rows, pitcher_rows, bvp_rows, season, phase)
    pitcher_recent = build_pitcher_recent(pitcher_rows, season, phase)
    bullpen_recent = build_bullpen_recent(pitcher_rows, season, phase)

    write_csv(paths["batterTotals"], BATTER_TOTAL_FIELDS, batter_totals)
    write_csv(paths["pitcherTotals"], PITCHER_TOTAL_FIELDS, pitcher_totals)
    write_csv(paths["teamTotals"], TEAM_TOTAL_FIELDS, team_totals)
    write_csv(paths["bvpTotals"], BVP_TOTAL_FIELDS, bvp_totals)
    write_csv(paths["batterRecent"], BATTER_RECENT_FIELDS, batter_recent)
    write_csv(paths["batterRecentVsHand"], BATTER_RECENT_VS_HAND_FIELDS, batter_recent_vs_hand)
    write_csv(paths["pitcherRecent"], PITCHER_RECENT_FIELDS, pitcher_recent)
    write_csv(paths["bullpenRecent"], BULLPEN_RECENT_FIELDS, bullpen_recent)

    summary = {
        "season": season,
        "phase": phase,
        "regularSeasonStart": REGULAR_SEASON_START_DATES.get(season),
        "inputRows": {
            "batters": len(batter_rows),
            "pitchers": len(pitcher_rows),
            "teams": len(team_rows),
            "bvp": len(bvp_rows),
        },
        "outputRows": {
            "batterTotals": len(batter_totals),
            "pitcherTotals": len(pitcher_totals),
            "teamTotals": len(team_totals),
            "bvpTotals": len(bvp_totals),
            "batterRecent": len(batter_recent),
            "batterRecentVsHand": len(batter_recent_vs_hand),
            "pitcherRecent": len(pitcher_recent),
            "bullpenRecent": len(bullpen_recent),
        },
        "files": {key: str(value) for key, value in paths.items()},
        "updatedAt": now_iso(),
    }

    write_json(paths["status"], summary)
    return summary


def player_statsapi_cross_reference(player_id: str, season: int = 2026) -> dict[str, Any]:
    result = {
        "playerId": player_id,
        "season": season,
        "hitting": {},
        "pitching": {},
    }

    for group in ["hitting", "pitching"]:
        try:
            payload = mlb_get(f"people/{player_id}/stats", {
                "stats": "season",
                "season": season,
                "group": group,
            })

            splits = payload.get("stats", [{}])[0].get("splits", [])
            if splits:
                result[group] = splits[0].get("stat", {})
        except Exception as error:
            result[group] = {"error": str(error)}

    return result


def find_local_player(player_name: str, season: int = 2026, kind: str = "batter") -> dict[str, Any]:
    paths = file_paths(season)

    if kind == "pitcher":
        rows = read_csv_rows(paths["pitcherTotals"])
        name_key = "player"
    else:
        rows = read_csv_rows(paths["batterTotals"])
        name_key = "player"

    target = clean(player_name).lower()

    for row in rows:
        if clean(row.get(name_key)).lower() == target:
            return row

    for row in rows:
        if target and target in clean(row.get(name_key)).lower():
            return row

    return {}


def cross_reference_player(player_name: str, season: int = 2026, kind: str = "batter") -> dict[str, Any]:
    local = find_local_player(player_name, season, kind)

    if not local:
        return {
            "player": player_name,
            "season": season,
            "kind": kind,
            "foundLocal": False,
            "error": "Player not found in local aggregate totals. Build features first or check spelling.",
        }

    player_id = clean(local.get("playerId"))
    remote = player_statsapi_cross_reference(player_id, season)

    if kind == "pitcher":
        remote_stats = remote.get("pitching", {})
        comparisons = {
            "strikeouts": {
                "local": to_float(local.get("strikeouts")),
                "mlbApi": to_float(remote_stats.get("strikeOuts")),
            },
            "hitsAllowed": {
                "local": to_float(local.get("hitsAllowed")),
                "mlbApi": to_float(remote_stats.get("hits")),
            },
            "earnedRuns": {
                "local": to_float(local.get("earnedRuns")),
                "mlbApi": to_float(remote_stats.get("earnedRuns")),
            },
            "walks": {
                "local": to_float(local.get("walks")),
                "mlbApi": to_float(remote_stats.get("baseOnBalls")),
            },
        }
    else:
        remote_stats = remote.get("hitting", {})
        comparisons = {
            "hits": {
                "local": to_float(local.get("hits")),
                "mlbApi": to_float(remote_stats.get("hits")),
            },
            "homeRuns": {
                "local": to_float(local.get("homeRuns")),
                "mlbApi": to_float(remote_stats.get("homeRuns")),
            },
            "totalBases": {
                "local": to_float(local.get("totalBases")),
                "mlbApi": to_float(remote_stats.get("totalBases")),
            },
            "strikeouts": {
                "local": to_float(local.get("strikeouts")),
                "mlbApi": to_float(remote_stats.get("strikeOuts")),
            },
        }

    for item in comparisons.values():
        item["difference"] = item["local"] - item["mlbApi"]

    return {
        "player": local.get("player"),
        "playerId": player_id,
        "season": season,
        "kind": kind,
        "foundLocal": True,
        "local": local,
        "mlbApi": remote_stats,
        "comparisons": comparisons,
        "note": "Differences can happen if local cache includes practice games, partial season ranges, or if MLB API season group uses a different game type.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build aggregate MLB feature files.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--season", type=int, default=2026)
    build.add_argument("--phase", default="regular", choices=["regular", "practice", "all"])

    cross = sub.add_parser("cross-reference")
    cross.add_argument("--season", type=int, default=2026)
    cross.add_argument("--player", required=True)
    cross.add_argument("--kind", default="batter", choices=["batter", "pitcher"])

    args = parser.parse_args()

    if args.command == "build":
        print(json.dumps(build_features(args.season, args.phase), indent=2))
    elif args.command == "cross-reference":
        print(json.dumps(cross_reference_player(args.player, args.season, args.kind), indent=2))


if __name__ == "__main__":
    main()
