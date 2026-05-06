from __future__ import annotations

"""Incremental MLB stats warehouse.

This collector is designed for daily autonomous use.

It stores:
- games
- batter game logs
- pitcher game logs
- team game logs
- batter-vs-pitcher plate appearances
- player index
- team index
- run status

Storage:
data/cache/incremental_stats/

Main behavior:
- First run backfills the selected season from start date through end date.
- Future runs skip already cached non-final games where appropriate.
- Final games are safely upserted by unique keys, so duplicates do not pile up.
"""

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request

try:
    import requests
except ImportError:  # requests is optional; urllib remains the fallback.
    requests = None
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache" / "incremental_stats"
RAW_DIR = CACHE_DIR / "raw"
RUN_DIR = CACHE_DIR / "runs"

MLB_BASE = "https://statsapi.mlb.com/api/v1"
SUPPORTED_SEASONS = {2024, 2025, 2026}

# For 2026, user-defined split:
# practice/spring games started 2026-03-01
# regular season starts 2026-03-25
REGULAR_SEASON_START_DATES = {
    2024: "2024-03-20",
    2025: "2025-03-18",
    2026: "2026-03-25",
}


def season_phase_for_date(date_label: str, season: int | None = None) -> str:
    if not season:
        season = int(str(date_label)[:4])

    regular_start = REGULAR_SEASON_START_DATES.get(season, f"{season}-03-25")
    return "regular" if str(date_label) >= regular_start else "practice"


def phase_allowed(date_label: str, season: int, requested_phase: str = "regular") -> bool:
    requested_phase = clean(requested_phase or "regular").lower()

    if requested_phase in {"all", "any"}:
        return True

    actual = season_phase_for_date(date_label, season)
    return actual == requested_phase

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

TEAM_ALIASES = {
    "KC": "KCR",
    "KCR": "KCR",
    "SD": "SDP",
    "SDP": "SDP",
    "SF": "SFG",
    "SFG": "SFG",
    "TB": "TBR",
    "TBR": "TBR",
    "WSH": "WSN",
    "WSN": "WSN",
    "CWS": "CHW",
    "CHW": "CHW",
    "OAK": "ATH",
    "ATH": "ATH",
    "AZ": "ARI",
    "ARI": "ARI",
    "ANA": "LAA",
    "LAA": "LAA",
}


GAME_FIELDS = [
    "season", "seasonPhase", "date", "gamePk", "gameDate", "status", "codedGameState",
    "away", "home", "awayName", "homeName", "awayScore", "homeScore",
    "awayProbablePitcher", "homeProbablePitcher", "venue", "final",
]

BATTER_FIELDS = [
    "season", "seasonPhase", "date", "gamePk", "side", "team", "opponent", "playerId", "player",
    "jersey", "position", "plateAppearances", "atBats", "runs", "hits", "doubles",
    "triples", "homeRuns", "rbi", "baseOnBalls", "strikeOuts", "stolenBases",
    "totalBases", "leftOnBase", "bats",
]

PITCHER_FIELDS = [
    "season", "seasonPhase", "date", "gamePk", "side", "team", "opponent", "playerId", "player",
    "jersey", "position", "inningsPitched", "runs", "earnedRuns", "hits", "homeRuns",
    "baseOnBalls", "strikeOuts", "battersFaced", "pitchesThrown", "strikes",
    "wins", "losses", "saves", "throws",
]

TEAM_FIELDS = [
    "season", "seasonPhase", "date", "gamePk", "side", "team", "opponent", "teamName",
    "runs", "hits", "homeRuns", "strikeOuts", "baseOnBalls", "atBats",
    "totalBases", "leftOnBase", "pitchingRuns", "pitchingHits",
    "pitchingStrikeOuts", "pitchingBaseOnBalls", "pitchingHomeRuns",
]

BVP_FIELDS = [
    "season", "seasonPhase", "date", "gamePk", "atBatIndex", "inning", "halfInning",
    "battingTeam", "pitchingTeam", "batterId", "batter", "pitcherId", "pitcher",
    "event", "eventType", "description", "rbi", "isPlateAppearance",
    "isAtBat", "hit", "homeRun", "walk", "strikeout", "totalBases",
]

PLAYER_INDEX_FIELDS = [
    "playerId", "player", "team", "role", "batterGames", "pitcherGames",
    "bvpPlateAppearances",
]

TEAM_INDEX_FIELDS = [
    "team", "teamName", "games",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


# Returns 0.0 for missing values. Appropriate for stat aggregation.
# For ML feature extraction use ml_prop_model.to_float() instead.
def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def normalize_team(value: Any) -> str:
    text = clean(value).upper()
    return TEAM_ALIASES.get(text, text)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def ensure_dirs() -> None:
    for path in [CACHE_DIR, RAW_DIR, RUN_DIR, RAW_DIR / "schedules", RAW_DIR / "boxscores", RAW_DIR / "live"]:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def upsert_csv(path: Path, key_fields: list[str], fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[tuple[str, ...], dict[str, str]] = {}

    if path.exists():
        for row in read_csv_rows(path):
            key = tuple(clean(row.get(field)) for field in key_fields)
            existing[key] = row

    before = len(existing)

    for row in rows:
        normalized = {field: clean(row.get(field, "")) for field in fieldnames}
        key = tuple(clean(normalized.get(field)) for field in key_fields)
        existing[key] = normalized

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in existing.values():
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    after = len(existing)

    return {
        "inputRows": len(rows),
        "beforeRows": before,
        "afterRows": after,
        "insertedOrUpdated": len(rows),
        "netNewRows": max(0, after - before),
    }


_HTTP_SESSION = requests.Session() if requests is not None else None
if _HTTP_SESSION is not None:
    _HTTP_SESSION.headers.update({"User-Agent": "baseball-prop-predictor"})


def fetch_json(url: str, timeout: int = 25, retries: int = 3) -> dict[str, Any]:
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            if _HTTP_SESSION is not None:
                response = _HTTP_SESSION.get(url, timeout=timeout)
                response.raise_for_status()
                return response.json()

            request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(1.5 * attempt)

    raise RuntimeError(f"Failed after {retries} attempts: {url} :: {last_error}")


def mlb_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return fetch_json(f"{MLB_BASE}/{endpoint}?{query}")


def date_range(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    out = []
    current = start

    while current <= end:
        out.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return out


def team_code(team: dict[str, Any]) -> str:
    name = clean(team.get("name"))
    if name in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[name]

    abbr = clean(team.get("abbreviation") or team.get("teamCode") or team.get("fileCode")).upper()
    return normalize_team(abbr)


def game_is_final(game: dict[str, Any]) -> bool:
    status = game.get("status", {})
    coded = clean(status.get("codedGameState")).upper()
    detailed = clean(status.get("detailedState")).lower()
    return coded == "F" or "final" in detailed


def stat(stats: dict[str, Any], key: str) -> str:
    value = stats.get(key, "")
    return "" if value is None else str(value)


def file_paths(season: int) -> dict[str, Path]:
    return {
        "games": CACHE_DIR / f"games_{season}.csv",
        "batters": CACHE_DIR / f"batter_game_logs_{season}.csv",
        "pitchers": CACHE_DIR / f"pitcher_game_logs_{season}.csv",
        "teams": CACHE_DIR / f"team_game_logs_{season}.csv",
        "bvp": CACHE_DIR / f"batter_vs_pitcher_pa_{season}.csv",
        "players": CACHE_DIR / f"player_index_{season}.csv",
        "teamIndex": CACHE_DIR / f"team_index_{season}.csv",
        "status": CACHE_DIR / f"status_{season}.json",
    }


def already_final_game_pks(season: int) -> set[str]:
    paths = file_paths(season)
    out = set()

    for row in read_csv_rows(paths["games"]):
        if clean(row.get("final")).lower() in {"true", "1", "yes"}:
            game_pk = clean(row.get("gamePk"))
            if game_pk:
                out.add(game_pk)

    return out


def fetch_schedule(date_label: str, force: bool = False) -> dict[str, Any]:
    ensure_dirs()
    path = RAW_DIR / "schedules" / f"schedule_{date_label}.json"

    if path.exists() and not force:
        payload = read_json(path, {})
    else:
        payload = mlb_get("schedule", {
            "sportId": 1,
            "startDate": date_label,
            "endDate": date_label,
            "hydrate": "probablePitcher,team",
        })
        write_json(path, payload)
        time.sleep(0.1)

    games = []
    season = int(date_label[:4])

    for day in payload.get("dates", []):
        for game in day.get("games", []):
            teams = game.get("teams", {})
            away_team = teams.get("away", {}).get("team", {})
            home_team = teams.get("home", {}).get("team", {})

            away = team_code(away_team)
            home = team_code(home_team)

            games.append({
                "season": season,
                "seasonPhase": season_phase_for_date(date_label, season),
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

    return {
        "date": date_label,
        "games": games,
    }


def fetch_boxscore(game_pk: str, force: bool = False) -> dict[str, Any]:
    path = RAW_DIR / "boxscores" / f"{game_pk}.json"

    if path.exists() and not force:
        return read_json(path, {})

    payload = fetch_json(f"{MLB_BASE}/game/{game_pk}/boxscore")
    write_json(path, payload)
    time.sleep(0.1)
    return payload


def fetch_live_feed(game_pk: str, force: bool = False) -> dict[str, Any]:
    path = RAW_DIR / "live" / f"{game_pk}.json"

    if path.exists() and not force:
        return read_json(path, {})

    url = f"{MLB_BASE}/game/{game_pk}/feed/live"

    try:
        payload = fetch_json(url)
    except RuntimeError as error:
        message = str(error)

        # Some early/spring games have boxscores but no live play-by-play feed.
        # That should not break the season stats warehouse.
        if "HTTP Error 404" in message or "Not Found" in message:
            payload = {
                "gamePk": game_pk,
                "unavailable": True,
                "reason": "MLB live feed not available for this game.",
                "liveData": {"plays": {"allPlays": []}},
            }
        else:
            raise

    write_json(path, payload)
    time.sleep(0.1)
    return payload


def extract_boxscore_logs(date_label: str, game: dict[str, Any], boxscore: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    season = int(date_label[:4])
    game_pk = clean(game.get("gamePk"))

    batter_rows = []
    pitcher_rows = []
    team_rows = []

    teams = boxscore.get("teams", {})

    for side in ["away", "home"]:
        team_obj = teams.get(side, {})
        team = team_obj.get("team", {})
        team_abbr = team_code(team) or clean(game.get(side)).upper()
        team_name = clean(team.get("name"))
        opponent = clean(game.get("home" if side == "away" else "away")).upper()

        players = team_obj.get("players", {})
        team_stats = team_obj.get("teamStats", {})
        batting_team_stats = team_stats.get("batting", {})
        pitching_team_stats = team_stats.get("pitching", {})

        team_rows.append({
            "season": season,
            "seasonPhase": season_phase_for_date(date_label, season),
            "date": date_label,
            "gamePk": game_pk,
            "side": side,
            "team": team_abbr,
            "opponent": opponent,
            "teamName": team_name,
            "runs": stat(batting_team_stats, "runs"),
            "hits": stat(batting_team_stats, "hits"),
            "homeRuns": stat(batting_team_stats, "homeRuns"),
            "strikeOuts": stat(batting_team_stats, "strikeOuts"),
            "baseOnBalls": stat(batting_team_stats, "baseOnBalls"),
            "atBats": stat(batting_team_stats, "atBats"),
            "totalBases": stat(batting_team_stats, "totalBases"),
            "leftOnBase": stat(batting_team_stats, "leftOnBase"),
            "pitchingRuns": stat(pitching_team_stats, "runs"),
            "pitchingHits": stat(pitching_team_stats, "hits"),
            "pitchingStrikeOuts": stat(pitching_team_stats, "strikeOuts"),
            "pitchingBaseOnBalls": stat(pitching_team_stats, "baseOnBalls"),
            "pitchingHomeRuns": stat(pitching_team_stats, "homeRuns"),
        })

        for player_key, player in players.items():
            person = player.get("person", {})
            player_id = clean(person.get("id")) or clean(player_key).replace("ID", "")
            player_name = clean(person.get("fullName"))
            position = clean(player.get("position", {}).get("abbreviation"))
            jersey = clean(player.get("jerseyNumber"))
            bats = clean(person.get("batSide", {}).get("code") or player.get("batSide", {}).get("code"))
            throws = clean(person.get("pitchHand", {}).get("code") or player.get("pitchHand", {}).get("code"))

            batting = player.get("stats", {}).get("batting", {})
            pitching = player.get("stats", {}).get("pitching", {})

            if batting:
                batter_rows.append({
                    "season": season,
                    "date": date_label,
                    "gamePk": game_pk,
                    "side": side,
                    "team": team_abbr,
                    "opponent": opponent,
                    "playerId": player_id,
                    "player": player_name,
                    "jersey": jersey,
                    "position": position,
                    "plateAppearances": stat(batting, "plateAppearances"),
                    "atBats": stat(batting, "atBats"),
                    "runs": stat(batting, "runs"),
                    "hits": stat(batting, "hits"),
                    "doubles": stat(batting, "doubles"),
                    "triples": stat(batting, "triples"),
                    "homeRuns": stat(batting, "homeRuns"),
                    "rbi": stat(batting, "rbi"),
                    "baseOnBalls": stat(batting, "baseOnBalls"),
                    "strikeOuts": stat(batting, "strikeOuts"),
                    "stolenBases": stat(batting, "stolenBases"),
                    "totalBases": stat(batting, "totalBases"),
                    "leftOnBase": stat(batting, "leftOnBase"),
                    "bats": bats,
                })

            if pitching:
                pitcher_rows.append({
                    "season": season,
                    "date": date_label,
                    "gamePk": game_pk,
                    "side": side,
                    "team": team_abbr,
                    "opponent": opponent,
                    "playerId": player_id,
                    "player": player_name,
                    "jersey": jersey,
                    "position": position,
                    "inningsPitched": stat(pitching, "inningsPitched"),
                    "runs": stat(pitching, "runs"),
                    "earnedRuns": stat(pitching, "earnedRuns"),
                    "hits": stat(pitching, "hits"),
                    "homeRuns": stat(pitching, "homeRuns"),
                    "baseOnBalls": stat(pitching, "baseOnBalls"),
                    "strikeOuts": stat(pitching, "strikeOuts"),
                    "battersFaced": stat(pitching, "battersFaced"),
                    "pitchesThrown": stat(pitching, "pitchesThrown"),
                    "strikes": stat(pitching, "strikes"),
                    "wins": stat(pitching, "wins"),
                    "losses": stat(pitching, "losses"),
                    "saves": stat(pitching, "saves"),
                    "throws": throws,
                })

    return {
        "batters": batter_rows,
        "pitchers": pitcher_rows,
        "teams": team_rows,
    }


def total_bases_from_event(event_type: str) -> int:
    event_type = clean(event_type).lower()
    if event_type == "single":
        return 1
    if event_type == "double":
        return 2
    if event_type == "triple":
        return 3
    if event_type == "home_run":
        return 4
    return 0


def extract_bvp_from_live_feed(date_label: str, game: dict[str, Any], live: dict[str, Any]) -> list[dict[str, Any]]:
    season = int(date_label[:4])
    game_pk = clean(game.get("gamePk"))
    rows = []

    all_plays = live.get("liveData", {}).get("plays", {}).get("allPlays", [])

    for play in all_plays:
        matchup = play.get("matchup", {})
        result = play.get("result", {})
        about = play.get("about", {})
        count = play.get("count", {})

        batter = matchup.get("batter", {})
        pitcher = matchup.get("pitcher", {})
        batting_team = matchup.get("battingTeam", {})
        pitching_team = matchup.get("pitchingTeam", {})

        event_type = clean(result.get("eventType"))
        event = clean(result.get("event"))
        description = clean(result.get("description"))

        total_bases = total_bases_from_event(event_type)

        rows.append({
            "season": season,
            "seasonPhase": season_phase_for_date(date_label, season),
            "date": date_label,
            "gamePk": game_pk,
            "atBatIndex": clean(about.get("atBatIndex")),
            "inning": clean(about.get("inning")),
            "halfInning": clean(about.get("halfInning")),
            "battingTeam": team_code(batting_team),
            "pitchingTeam": team_code(pitching_team),
            "batterId": clean(batter.get("id")),
            "batter": clean(batter.get("fullName")),
            "pitcherId": clean(pitcher.get("id")),
            "pitcher": clean(pitcher.get("fullName")),
            "event": event,
            "eventType": event_type,
            "description": description,
            "rbi": clean(result.get("rbi")),
            "isPlateAppearance": clean(about.get("isComplete")),
            "isAtBat": "1" if event_type not in {"walk", "intent_walk", "hit_by_pitch", "sac_bunt", "sac_fly", "catcher_interf"} else "0",
            "hit": "1" if event_type in {"single", "double", "triple", "home_run"} else "0",
            "homeRun": "1" if event_type == "home_run" else "0",
            "walk": "1" if event_type in {"walk", "intent_walk"} else "0",
            "strikeout": "1" if "strikeout" in event_type else "0",
            "totalBases": total_bases,
        })

    return rows


def rebuild_indexes(season: int) -> dict[str, Any]:
    paths = file_paths(season)

    players: dict[tuple[str, str], dict[str, Any]] = {}
    teams: dict[str, dict[str, Any]] = {}

    for row in read_csv_rows(paths["batters"]):
        key = (clean(row.get("playerId")), clean(row.get("player")))
        if not key[1]:
            continue

        item = players.setdefault(key, {
            "playerId": key[0],
            "player": key[1],
            "team": clean(row.get("team")),
            "role": "batter",
            "batterGames": 0,
            "pitcherGames": 0,
            "bvpPlateAppearances": 0,
        })

        item["batterGames"] = int(item.get("batterGames", 0)) + 1
        if row.get("team"):
            item["team"] = clean(row.get("team"))

    for row in read_csv_rows(paths["pitchers"]):
        key = (clean(row.get("playerId")), clean(row.get("player")))
        if not key[1]:
            continue

        item = players.setdefault(key, {
            "playerId": key[0],
            "player": key[1],
            "team": clean(row.get("team")),
            "role": "pitcher",
            "batterGames": 0,
            "pitcherGames": 0,
            "bvpPlateAppearances": 0,
        })

        item["pitcherGames"] = int(item.get("pitcherGames", 0)) + 1
        item["role"] = "two-way" if int(item.get("batterGames", 0)) else "pitcher"
        if row.get("team"):
            item["team"] = clean(row.get("team"))

    for row in read_csv_rows(paths["bvp"]):
        batter_key = (clean(row.get("batterId")), clean(row.get("batter")))
        pitcher_key = (clean(row.get("pitcherId")), clean(row.get("pitcher")))

        if batter_key[1]:
            item = players.setdefault(batter_key, {
                "playerId": batter_key[0],
                "player": batter_key[1],
                "team": clean(row.get("battingTeam")),
                "role": "batter",
                "batterGames": 0,
                "pitcherGames": 0,
                "bvpPlateAppearances": 0,
            })
            item["bvpPlateAppearances"] = int(item.get("bvpPlateAppearances", 0)) + 1

        if pitcher_key[1]:
            item = players.setdefault(pitcher_key, {
                "playerId": pitcher_key[0],
                "player": pitcher_key[1],
                "team": clean(row.get("pitchingTeam")),
                "role": "pitcher",
                "batterGames": 0,
                "pitcherGames": 0,
                "bvpPlateAppearances": 0,
            })
            item["bvpPlateAppearances"] = int(item.get("bvpPlateAppearances", 0)) + 1

    for row in read_csv_rows(paths["teams"]):
        team = normalize_team(row.get("team"))
        if not team:
            continue

        item = teams.setdefault(team, {
            "team": team,
            "teamName": clean(row.get("teamName")),
            "games": 0,
        })

        item["games"] = int(item.get("games", 0)) + 1
        if row.get("teamName"):
            item["teamName"] = clean(row.get("teamName"))

    with paths["players"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAYER_INDEX_FIELDS)
        writer.writeheader()
        for item in sorted(players.values(), key=lambda x: clean(x.get("player")).lower()):
            writer.writerow({field: item.get(field, "") for field in PLAYER_INDEX_FIELDS})

    with paths["teamIndex"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEAM_INDEX_FIELDS)
        writer.writeheader()
        for item in sorted(teams.values(), key=lambda x: clean(x.get("team"))):
            writer.writerow({field: item.get(field, "") for field in TEAM_INDEX_FIELDS})

    return {
        "players": len(players),
        "teams": len(teams),
        "playerIndex": str(paths["players"]),
        "teamIndex": str(paths["teamIndex"]),
    }


def catchup_stats(
    season: int = 2026,
    start_date: str = "",
    end_date: str = "",
    force: bool = False,
    max_dates: int = 0,
    season_phase: str = "regular",
) -> dict[str, Any]:
    ensure_dirs()

    if season not in SUPPORTED_SEASONS:
        raise ValueError("Only 2024, 2025, and 2026 are supported.")

    if not start_date:
        start_date = f"{season}-03-01"
    if not end_date:
        end_date = today()

    paths = file_paths(season)
    final_cached = already_final_game_pks(season)
    running_counts = {
        "games": len(read_csv_rows(paths["games"])),
        "batters": len(read_csv_rows(paths["batters"])),
        "pitchers": len(read_csv_rows(paths["pitchers"])),
        "teams": len(read_csv_rows(paths["teams"])),
        "bvp": len(read_csv_rows(paths["bvp"])),
        "players": None,
        "teamIndex": None,
    }

    processed_dates = 0
    games_seen = 0
    final_games_seen = 0
    skipped_final_cached = 0
    boxscores_read = 0
    live_feeds_read = 0

    total_upserts = {
        "games": {"inputRows": 0, "netNewRows": 0},
        "batters": {"inputRows": 0, "netNewRows": 0},
        "pitchers": {"inputRows": 0, "netNewRows": 0},
        "teams": {"inputRows": 0, "netNewRows": 0},
        "bvp": {"inputRows": 0, "netNewRows": 0},
    }

    errors = []

    for date_label in date_range(start_date, end_date):
        if max_dates and processed_dates >= max_dates:
            break

        if not phase_allowed(date_label, season, season_phase):
            continue

        processed_dates += 1

        day_games = []
        day_batters = []
        day_pitchers = []
        day_teams = []
        day_bvp = []

        try:
            schedule = fetch_schedule(date_label, force=force)
        except Exception as error:
            errors.append({"date": date_label, "stage": "schedule", "error": str(error)})
            continue

        for game in schedule.get("games", []):
            games_seen += 1
            day_games.append(game)

            game_pk = clean(game.get("gamePk"))
            if not game.get("final"):
                continue

            final_games_seen += 1

            if game_pk in final_cached and not force:
                skipped_final_cached += 1
                continue

            try:
                boxscore = fetch_boxscore(game_pk, force=force)
                boxscores_read += 1
                extracted = extract_boxscore_logs(date_label, game, boxscore)
                day_batters.extend(extracted["batters"])
                day_pitchers.extend(extracted["pitchers"])
                day_teams.extend(extracted["teams"])
            except Exception as error:
                errors.append({"date": date_label, "gamePk": game_pk, "stage": "boxscore", "error": str(error)})

            try:
                live = fetch_live_feed(game_pk, force=force)
                live_feeds_read += 1
                day_bvp.extend(extract_bvp_from_live_feed(date_label, game, live))
            except Exception as error:
                errors.append({"date": date_label, "gamePk": game_pk, "stage": "live_feed_bvp", "error": str(error)})

        # Save progress after every date so interrupted runs keep completed work.
        day_upserts = {
            "games": upsert_csv(paths["games"], ["gamePk"], GAME_FIELDS, day_games),
            "batters": upsert_csv(paths["batters"], ["gamePk", "playerId"], BATTER_FIELDS, day_batters),
            "pitchers": upsert_csv(paths["pitchers"], ["gamePk", "playerId"], PITCHER_FIELDS, day_pitchers),
            "teams": upsert_csv(paths["teams"], ["gamePk", "team"], TEAM_FIELDS, day_teams),
            "bvp": upsert_csv(paths["bvp"], ["gamePk", "atBatIndex"], BVP_FIELDS, day_bvp),
        }

        for key, value in day_upserts.items():
            total_upserts[key]["inputRows"] += int(value.get("inputRows", 0))
            total_upserts[key]["netNewRows"] += int(value.get("netNewRows", 0))

        for key, value in day_upserts.items():
            running_counts[key] += int(value.get("netNewRows", 0))

        final_cached.update(
            clean(game.get("gamePk"))
            for game in day_games
            if game.get("final") and clean(game.get("gamePk"))
        )

        partial_counts = dict(running_counts)

        partial_summary = {
            "season": season,
            "startDate": start_date,
            "endDate": end_date,
            "lastCompletedDate": date_label,
            "force": force,
            "seasonPhase": season_phase,
            "regularSeasonStart": REGULAR_SEASON_START_DATES.get(season),
            "maxDates": max_dates,
            "processedDates": processed_dates,
            "gamesSeen": games_seen,
            "finalGamesSeen": final_games_seen,
            "skippedFinalCached": skipped_final_cached,
            "boxscoresRead": boxscores_read,
            "liveFeedsRead": live_feeds_read,
            "upserts": total_upserts,
            "rowCounts": partial_counts,
            "files": {key: str(value) for key, value in paths.items()},
            "errors": errors[-50:],
            "errorCount": len(errors),
            "updatedAt": now_iso(),
            "inProgress": True,
        }

        write_json(paths["status"], partial_summary)
        print(
            f"{date_label}: games={len(day_games)} batters={len(day_batters)} "
            f"pitchers={len(day_pitchers)} teams={len(day_teams)} bvp={len(day_bvp)}",
            flush=True,
        )

    indexes = rebuild_indexes(season)

    feature_build = None
    try:
        from build_incremental_features import build_features

        feature_build = build_features(season=season, phase=season_phase)
    except Exception as feature_error:
        feature_build = {"error": str(feature_error)}

    row_counts = {
        "games": len(read_csv_rows(paths["games"])),
        "batters": len(read_csv_rows(paths["batters"])),
        "pitchers": len(read_csv_rows(paths["pitchers"])),
        "teams": len(read_csv_rows(paths["teams"])),
        "bvp": len(read_csv_rows(paths["bvp"])),
        "players": len(read_csv_rows(paths["players"])),
        "teamIndex": len(read_csv_rows(paths["teamIndex"])),
    }

    summary = {
        "season": season,
        "startDate": start_date,
        "endDate": end_date,
        "force": force,
        "seasonPhase": season_phase,
        "regularSeasonStart": REGULAR_SEASON_START_DATES.get(season),
        "maxDates": max_dates,
        "processedDates": processed_dates,
        "gamesSeen": games_seen,
        "finalGamesSeen": final_games_seen,
        "skippedFinalCached": skipped_final_cached,
        "boxscoresRead": boxscores_read,
        "liveFeedsRead": live_feeds_read,
        "upserts": total_upserts,
        "indexes": indexes,
        "featureBuild": feature_build,
        "rowCounts": row_counts,
        "files": {key: str(value) for key, value in paths.items()},
        "errors": errors[:50],
        "errorCount": len(errors),
        "updatedAt": now_iso(),
        "inProgress": False,
    }

    write_json(paths["status"], summary)
    write_json(RUN_DIR / f"incremental_stats_{season}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json", summary)

    return summary


def status(season: int = 2026) -> dict[str, Any]:
    ensure_dirs()
    paths = file_paths(season)
    payload = read_json(paths["status"], {})
    payload["files"] = {key: str(value) for key, value in paths.items()}
    payload["rowCounts"] = {
        "games": len(read_csv_rows(paths["games"])),
        "batters": len(read_csv_rows(paths["batters"])),
        "pitchers": len(read_csv_rows(paths["pitchers"])),
        "teams": len(read_csv_rows(paths["teams"])),
        "bvp": len(read_csv_rows(paths["bvp"])),
        "players": len(read_csv_rows(paths["players"])),
        "teamIndex": len(read_csv_rows(paths["teamIndex"])),
    }

    phase_breakdown = {"regular": 0, "practice": 0, "unknown": 0}
    for row in read_csv_rows(paths["games"]):
        phase = clean(row.get("seasonPhase")) or season_phase_for_date(row.get("date", ""), season)
        if phase not in phase_breakdown:
            phase = "unknown"
        phase_breakdown[phase] += 1

    payload["phaseBreakdown"] = phase_breakdown
    payload["regularSeasonStart"] = REGULAR_SEASON_START_DATES.get(season)
    return payload


def lookup(query: str = "", kind: str = "all", season: int = 2026, limit: int = 20) -> dict[str, Any]:
    paths = file_paths(season)
    q = clean(query).lower()
    results = []

    if kind in {"all", "player", "batter", "pitcher"}:
        for row in read_csv_rows(paths["players"]):
            name = clean(row.get("player"))
            team = clean(row.get("team"))
            role = clean(row.get("role"))

            if kind == "pitcher" and role not in {"pitcher", "two-way"}:
                continue
            if kind == "batter" and role not in {"batter", "two-way"}:
                continue

            hay = f"{name} {team} {role}".lower()
            if not q or name.lower().startswith(q) or any(part.startswith(q) for part in name.lower().split()) or q in hay:
                results.append({
                    "type": "player",
                    "playerId": clean(row.get("playerId")),
                    "name": name,
                    "team": team,
                    "role": role,
                    "label": f"{name} ? {team} ? {role}",
                })

    if kind in {"all", "team"}:
        for row in read_csv_rows(paths["teamIndex"]):
            team = clean(row.get("team"))
            name = clean(row.get("teamName"))
            hay = f"{team} {name}".lower()
            if not q or team.lower().startswith(q) or name.lower().startswith(q) or q in hay:
                results.append({
                    "type": "team",
                    "team": team,
                    "name": name,
                    "label": f"{team} ? {name}",
                })

    return {
        "season": season,
        "query": query,
        "kind": kind,
        "count": min(len(results), limit),
        "results": results[:limit],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Incremental MLB stats collector.")
    sub = parser.add_subparsers(dest="command", required=True)

    catch = sub.add_parser("catchup")
    catch.add_argument("--season", type=int, default=2026)
    catch.add_argument("--start-date", default="")
    catch.add_argument("--end-date", default="")
    catch.add_argument("--force", action="store_true")
    catch.add_argument("--max-dates", type=int, default=0)
    catch.add_argument("--season-phase", default="regular", choices=["regular", "practice", "all"])

    stat_cmd = sub.add_parser("status")
    stat_cmd.add_argument("--season", type=int, default=2026)

    lookup_cmd = sub.add_parser("lookup")
    lookup_cmd.add_argument("--season", type=int, default=2026)
    lookup_cmd.add_argument("--query", default="")
    lookup_cmd.add_argument("--kind", default="all")
    lookup_cmd.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "catchup":
        print(json.dumps(catchup_stats(args.season, args.start_date, args.end_date, args.force, args.max_dates, args.season_phase), indent=2))
    elif args.command == "status":
        print(json.dumps(status(args.season), indent=2))
    elif args.command == "lookup":
        print(json.dumps(lookup(args.query, args.kind, args.season, args.limit), indent=2))


if __name__ == "__main__":
    main()
