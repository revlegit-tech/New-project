from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
SUMMARY_DIR = WAREHOUSE_DIR / "summaries"
RAW_DIR = WAREHOUSE_DIR / "raw"

MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"

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
    "Athletics": "ATH",
    "Oakland Athletics": "ATH",
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

ALIASES = {
    "KC": "KCR",
    "SD": "SDP",
    "SF": "SFG",
    "TB": "TBR",
    "WSH": "WSN",
    "CWS": "CHW",
    "OAK": "ATH",
}


def ensure_dirs() -> None:
    for path in [WAREHOUSE_DIR, SUMMARY_DIR, RAW_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str, timeout: int = 45) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def mlb_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return fetch_json(f"{MLB_STATS_API_BASE}/{endpoint}?{query}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def team_code(team: dict[str, Any]) -> str:
    name = str(team.get("name") or "").strip()
    if name in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[name]

    abbr = str(team.get("abbreviation") or team.get("teamCode") or team.get("fileCode") or "").upper()
    return ALIASES.get(abbr, abbr)


def game_is_final(game: dict[str, Any]) -> bool:
    status = game.get("status", {})
    coded = str(status.get("codedGameState", "")).upper()
    detailed = str(status.get("detailedState", "")).lower()
    return coded == "F" or "final" in detailed


def sync_mlb_schedule(date_label: str) -> dict[str, Any]:
    ensure_dirs()

    payload = mlb_get("schedule", {
        "sportId": 1,
        "startDate": date_label,
        "endDate": date_label,
        "hydrate": "probablePitcher,team",
    })

    games = []

    for day in payload.get("dates", []):
        for game in day.get("games", []):
            teams = game.get("teams", {})
            away_team = teams.get("away", {}).get("team", {})
            home_team = teams.get("home", {}).get("team", {})

            away = team_code(away_team)
            home = team_code(home_team)

            games.append({
                "date": date_label,
                "gamePk": game.get("gamePk"),
                "gameDate": game.get("gameDate"),
                "status": game.get("status", {}).get("detailedState", ""),
                "codedGameState": game.get("status", {}).get("codedGameState", ""),
                "away": away,
                "home": home,
                "awayName": away_team.get("name", ""),
                "homeName": home_team.get("name", ""),
                "awayScore": teams.get("away", {}).get("score"),
                "homeScore": teams.get("home", {}).get("score"),
                "awayProbablePitcher": teams.get("away", {}).get("probablePitcher", {}).get("fullName", ""),
                "homeProbablePitcher": teams.get("home", {}).get("probablePitcher", {}).get("fullName", ""),
                "venue": game.get("venue", {}).get("name", ""),
                "final": game_is_final(game),
            })

    write_json(RAW_DIR / f"mlb_schedule_{date_label}.json", payload)
    write_json(SUMMARY_DIR / f"games_{date_label}.json", games)

    return {
        "games": games,
        "gameCount": len(games),
        "finalGames": sum(1 for game in games if game.get("final")),
    }


def sync_date(date_label: str) -> dict[str, Any]:
    """Compatibility wrapper used by season_auto_collector.

    The collector expects sync_date(). This module currently exposes
    sync_mlb_schedule(), so sync_date() returns the same schedule summary
    using the keys the collector/run index expects.
    """
    schedule = sync_mlb_schedule(date_label)
    games = schedule.get("games", [])

    return {
        "date": date_label,
        "mlbGames": schedule.get("gameCount", len(games)),
        "finalGames": schedule.get("finalGames", 0),
        "boxscoresSaved": 0,
        "propCount": "",
        "schedule": schedule,
    }
