from __future__ import annotations

"""Cached MLB season stats storage.

Purpose:
- Pull already-played MLB games for 2024/2025/2026.
- Save local cached batter, pitcher, and team logs.
- Upsert rows by game/player/team so duplicates do not pile up.
- Provide lookup data for UI autocomplete.
- Avoid re-pulling data every time the app opens.

Main files:
data/cache/season_stats/batter_game_logs_2026.csv
data/cache/season_stats/pitcher_game_logs_2026.csv
data/cache/season_stats/team_game_logs_2026.csv
data/cache/season_stats/games_2026.csv
data/cache/season_stats/player_index_2026.csv
data/cache/season_stats/team_index_2026.csv
data/cache/season_stats/status_2026.json
"""

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache" / "season_stats"
RAW_DIR = CACHE_DIR / "raw"

SUPPORTED_YEARS = {2024, 2025, 2026}
MLB_BASE = "https://statsapi.mlb.com/api/v1"

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


def clean(value: Any) -> str:
    return str(value or "").strip()


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


def normalize_team(value: Any) -> str:
    text = clean(value).upper()
    return TEAM_ALIASES.get(text, text)


def ensure_dirs() -> None:
    for path in [CACHE_DIR, RAW_DIR]:
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


def fetch_json(url: str, timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def upsert_csv(path: Path, key_fields: list[str], fieldnames: list[str], rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[tuple[str, ...], dict[str, str]] = {}

    if path.exists():
        for row in read_csv_rows(path):
            key = tuple(clean(row.get(field)) for field in key_fields)
            existing[key] = row

    for row in rows:
        normalized = {field: clean(row.get(field, "")) for field in fieldnames}
        key = tuple(clean(normalized.get(field)) for field in key_fields)
        existing[key] = normalized

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in existing.values():
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    return len(rows)


def fetch_schedule_for_date(date_label: str) -> dict[str, Any]:
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

    write_json(RAW_DIR / f"schedule_{date_label}.json", payload)
    return {"date": date_label, "games": games}


def fetch_boxscore(game_pk: str, force: bool = False) -> dict[str, Any]:
    path = RAW_DIR / "boxscores" / f"{game_pk}.json"
    if path.exists() and not force:
        return read_json(path, {})

    payload = fetch_json(f"{MLB_BASE}/game/{game_pk}/boxscore")
    write_json(path, payload)
    time.sleep(0.15)
    return payload


def extract_logs_from_boxscore(date_label: str, game: dict[str, Any], boxscore: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    batter_rows = []
    pitcher_rows = []
    team_rows = []

    year = int(date_label[:4])
    game_pk = clean(game.get("gamePk"))

    teams = boxscore.get("teams", {})

    for side in ["away", "home"]:
        team_obj = teams.get(side, {})
        team = team_obj.get("team", {})
        team_abbr = team_code(team) or clean(game.get(side)).upper()
        team_name = clean(team.get("name"))
        players = team_obj.get("players", {})
        team_stats = team_obj.get("teamStats", {})
        batting_team_stats = team_stats.get("batting", {})
        pitching_team_stats = team_stats.get("pitching", {})

        opponent = clean(game.get("home" if side == "away" else "away")).upper()

        team_rows.append({
            "date": date_label,
            "season": year,
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
                    "date": date_label,
                    "season": year,
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
                    "date": date_label,
                    "season": year,
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

    return {"batters": batter_rows, "pitchers": pitcher_rows, "teams": team_rows}


BATTER_FIELDS = [
    "date", "season", "gamePk", "side", "team", "opponent", "playerId", "player", "jersey", "position",
    "plateAppearances", "atBats", "runs", "hits", "doubles", "triples", "homeRuns",
    "rbi", "baseOnBalls", "strikeOuts", "stolenBases", "totalBases", "leftOnBase", "bats",
]

PITCHER_FIELDS = [
    "date", "season", "gamePk", "side", "team", "opponent", "playerId", "player", "jersey", "position",
    "inningsPitched", "runs", "earnedRuns", "hits", "homeRuns", "baseOnBalls",
    "strikeOuts", "battersFaced", "pitchesThrown", "strikes", "wins", "losses", "saves", "throws",
]

TEAM_FIELDS = [
    "date", "season", "gamePk", "side", "team", "opponent", "teamName", "runs", "hits",
    "homeRuns", "strikeOuts", "baseOnBalls", "atBats", "totalBases", "leftOnBase",
    "pitchingRuns", "pitchingHits", "pitchingStrikeOuts", "pitchingBaseOnBalls", "pitchingHomeRuns",
]

GAME_FIELDS = [
    "date", "gamePk", "gameDate", "status", "codedGameState", "away", "home", "awayName", "homeName",
    "awayScore", "homeScore", "awayProbablePitcher", "homeProbablePitcher", "venue", "final",
]


def rebuild_indexes(season: int) -> dict[str, Any]:
    batter_path = CACHE_DIR / f"batter_game_logs_{season}.csv"
    pitcher_path = CACHE_DIR / f"pitcher_game_logs_{season}.csv"
    team_path = CACHE_DIR / f"team_game_logs_{season}.csv"

    players: dict[tuple[str, str], dict[str, Any]] = {}
    teams: dict[str, dict[str, Any]] = {}

    for row in read_csv_rows(batter_path):
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
        })
        item["batterGames"] = int(item.get("batterGames", 0)) + 1
        if row.get("team"):
            item["team"] = clean(row.get("team"))

    for row in read_csv_rows(pitcher_path):
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
        })
        item["pitcherGames"] = int(item.get("pitcherGames", 0)) + 1
        item["role"] = "two-way" if int(item.get("batterGames", 0)) else "pitcher"
        if row.get("team"):
            item["team"] = clean(row.get("team"))

    for row in read_csv_rows(team_path):
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

    player_fields = ["playerId", "player", "team", "role", "batterGames", "pitcherGames"]
    team_fields = ["team", "teamName", "games"]

    player_index = CACHE_DIR / f"player_index_{season}.csv"
    team_index = CACHE_DIR / f"team_index_{season}.csv"

    with player_index.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=player_fields)
        writer.writeheader()
        for item in sorted(players.values(), key=lambda x: clean(x.get("player")).lower()):
            writer.writerow({field: item.get(field, "") for field in player_fields})

    with team_index.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=team_fields)
        writer.writeheader()
        for item in sorted(teams.values(), key=lambda x: clean(x.get("team"))):
            writer.writerow({field: item.get(field, "") for field in team_fields})

    return {
        "playerIndex": str(player_index),
        "teamIndex": str(team_index),
        "players": len(players),
        "teams": len(teams),
    }


def backfill_played_games(season: int = 2026, start_date: str = "", end_date: str = "", force: bool = False) -> dict[str, Any]:
    ensure_dirs()

    if season not in SUPPORTED_YEARS:
        raise ValueError("Only 2024, 2025, and 2026 are supported.")

    if not start_date:
        start_date = f"{season}-03-01"
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    all_games = []
    batter_rows = []
    pitcher_rows = []
    team_rows = []
    boxscores_fetched = 0
    final_games = 0

    for date_label in date_range(start_date, end_date):
        schedule = fetch_schedule_for_date(date_label)
        games = schedule.get("games", [])
        all_games.extend(games)

        for game in games:
            if not game.get("final"):
                continue

            final_games += 1
            game_pk = clean(game.get("gamePk"))
            if not game_pk:
                continue

            boxscore = fetch_boxscore(game_pk, force=force)
            if boxscore:
                boxscores_fetched += 1
                extracted = extract_logs_from_boxscore(date_label, game, boxscore)
                batter_rows.extend(extracted["batters"])
                pitcher_rows.extend(extracted["pitchers"])
                team_rows.extend(extracted["teams"])

    games_file = CACHE_DIR / f"games_{season}.csv"
    batter_file = CACHE_DIR / f"batter_game_logs_{season}.csv"
    pitcher_file = CACHE_DIR / f"pitcher_game_logs_{season}.csv"
    team_file = CACHE_DIR / f"team_game_logs_{season}.csv"

    games_upserted = upsert_csv(games_file, ["gamePk"], GAME_FIELDS, all_games)
    batter_upserted = upsert_csv(batter_file, ["gamePk", "playerId"], BATTER_FIELDS, batter_rows)
    pitcher_upserted = upsert_csv(pitcher_file, ["gamePk", "playerId"], PITCHER_FIELDS, pitcher_rows)
    team_upserted = upsert_csv(team_file, ["gamePk", "team"], TEAM_FIELDS, team_rows)

    indexes = rebuild_indexes(season)

    status = {
        "season": season,
        "startDate": start_date,
        "endDate": end_date,
        "gamesFound": len(all_games),
        "finalGames": final_games,
        "boxscoresFetched": boxscores_fetched,
        "gamesUpserted": games_upserted,
        "batterRowsUpserted": batter_upserted,
        "pitcherRowsUpserted": pitcher_upserted,
        "teamRowsUpserted": team_upserted,
        "gamesFile": str(games_file),
        "batterFile": str(batter_file),
        "pitcherFile": str(pitcher_file),
        "teamFile": str(team_file),
        "indexes": indexes,
        "updatedAt": datetime.utcnow().isoformat() + "Z",
    }

    write_json(CACHE_DIR / f"status_{season}.json", status)
    return status


def status(season: int = 2026) -> dict[str, Any]:
    ensure_dirs()

    payload = read_json(CACHE_DIR / f"status_{season}.json", {})
    payload["files"] = {
        "games": str(CACHE_DIR / f"games_{season}.csv"),
        "batters": str(CACHE_DIR / f"batter_game_logs_{season}.csv"),
        "pitchers": str(CACHE_DIR / f"pitcher_game_logs_{season}.csv"),
        "teams": str(CACHE_DIR / f"team_game_logs_{season}.csv"),
        "players": str(CACHE_DIR / f"player_index_{season}.csv"),
        "teamIndex": str(CACHE_DIR / f"team_index_{season}.csv"),
    }
    payload["rowCounts"] = {
        "games": len(read_csv_rows(CACHE_DIR / f"games_{season}.csv")),
        "batters": len(read_csv_rows(CACHE_DIR / f"batter_game_logs_{season}.csv")),
        "pitchers": len(read_csv_rows(CACHE_DIR / f"pitcher_game_logs_{season}.csv")),
        "teams": len(read_csv_rows(CACHE_DIR / f"team_game_logs_{season}.csv")),
        "players": len(read_csv_rows(CACHE_DIR / f"player_index_{season}.csv")),
        "teamIndex": len(read_csv_rows(CACHE_DIR / f"team_index_{season}.csv")),
    }

    return payload


def lookup(query: str = "", kind: str = "all", season: int = 2026, limit: int = 20) -> dict[str, Any]:
    q = clean(query).lower()
    results = []

    if kind in {"all", "player", "pitcher", "batter"}:
        for row in read_csv_rows(CACHE_DIR / f"player_index_{season}.csv"):
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
        for row in read_csv_rows(CACHE_DIR / f"team_index_{season}.csv"):
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
    parser = argparse.ArgumentParser(description="Cache played MLB season stats.")
    sub = parser.add_subparsers(dest="command", required=True)

    backfill = sub.add_parser("backfill")
    backfill.add_argument("--season", type=int, default=2026)
    backfill.add_argument("--start-date", default="")
    backfill.add_argument("--end-date", default="")
    backfill.add_argument("--force", action="store_true")

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--season", type=int, default=2026)

    lookup_parser = sub.add_parser("lookup")
    lookup_parser.add_argument("--season", type=int, default=2026)
    lookup_parser.add_argument("--query", default="")
    lookup_parser.add_argument("--kind", default="all")
    lookup_parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "backfill":
        print(json.dumps(backfill_played_games(args.season, args.start_date, args.end_date, args.force), indent=2))
    elif args.command == "status":
        print(json.dumps(status(args.season), indent=2))
    elif args.command == "lookup":
        print(json.dumps(lookup(args.query, args.kind, args.season, args.limit), indent=2))


if __name__ == "__main__":
    main()
