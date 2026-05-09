from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from mlb_app.domain.team_game_markets import TEAM_ABBRS, autofill_matchup, norm_team, search_matchups

ROOT = Path(__file__).resolve().parents[2]
STATS_DIR = ROOT / "data" / "cache" / "incremental_stats"
CLOUD_SUMMARY_DIR = ROOT / "data" / "cloud" / "summaries"
_CSV_CACHE: dict[tuple[str, int, int], list[dict[str, str]]] = {}


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm(value: Any) -> str:
    text = clean(value).lower().replace(".", "").replace(",", "")
    return " ".join(text.split())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _CSV_CACHE.get(key)
    if cached is not None:
        return cached
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _CSV_CACHE[key] = rows
    return rows


def first_value(row: dict[str, Any], names: list[str]) -> str:
    lower = {clean(k).lower(): v for k, v in row.items()}
    for name in names:
        key = clean(name).lower()
        if key in lower and clean(lower[key]):
            return clean(lower[key])
    return ""


def player_index_rows(season: int) -> list[dict[str, str]]:
    rows = read_csv_rows(STATS_DIR / f"player_index_{season}.csv")
    if rows:
        return rows

    # Fallback from totals files if player_index is not available.
    out = []
    for source, kind in [
        (STATS_DIR / f"batter_totals_{season}.csv", "batter"),
        (STATS_DIR / f"pitcher_totals_{season}.csv", "pitcher"),
    ]:
        for row in read_csv_rows(source):
            out.append({
                "player": first_value(row, ["player", "name", "fullName"]),
                "playerId": first_value(row, ["playerId", "id", "mlbId", "personId"]),
                "team": first_value(row, ["team", "teamAbbr", "team_abbr"]),
                "kind": kind,
            })
    return out


def games_for_date(season: int, date_label: str) -> list[dict[str, str]]:
    rows = [
        row for row in read_csv_rows(STATS_DIR / f"games_{season}.csv")
        if clean(row.get("date")) == clean(date_label)
    ]
    if rows:
        return rows

    cloud_path = CLOUD_SUMMARY_DIR / f"games_{clean(date_label)[:10]}.json"
    if cloud_path.exists():
        try:
            payload = json.loads(cloud_path.read_text(encoding="utf-8"))
            return [dict(row) for row in payload if clean(row.get("date")) == clean(date_label)]
        except Exception:
            return []

    return []


def player_team_from_logs(season: int, date_label: str, player: str, kind: str = "") -> str:
    target = norm(player)

    files = []
    if kind in {"", "batter"}:
        files.append(STATS_DIR / f"batter_game_logs_{season}.csv")
    if kind in {"", "pitcher"}:
        files.append(STATS_DIR / f"pitcher_game_logs_{season}.csv")

    for path in files:
        for row in read_csv_rows(path):
            if date_label and clean(row.get("date")) != clean(date_label):
                continue
            if norm(row.get("player")) == target:
                return clean(row.get("team")).upper()

    return ""


def find_player(season: int, query: str, limit: int = 10) -> list[dict[str, Any]]:
    target = norm(query)
    if not target:
        return []

    # Prefer real prop roles over generic player-index entries.
    role_priority = {
        "batter": 3,
        "pitcher": 3,
        "player": 1,
    }

    best_by_player_team: dict[tuple[str, str], dict[str, Any]] = {}

    sources = [
        (STATS_DIR / f"batter_totals_{season}.csv", "batter"),
        (STATS_DIR / f"pitcher_totals_{season}.csv", "pitcher"),
        (STATS_DIR / f"player_index_{season}.csv", "player"),
    ]

    for path, kind in sources:
        for row in read_csv_rows(path):
            player = first_value(row, ["player", "name", "fullName", "full_name"])
            if not player:
                continue

            name_norm = norm(player)
            if not name_norm.startswith(target) and target not in name_norm:
                continue

            player_id = first_value(row, ["playerId", "id", "mlbId", "personId"])
            team = first_value(row, ["team", "teamAbbr", "team_abbr"]).upper()

            key = (name_norm, team)
            score = 100 if name_norm.startswith(target) else 50
            score += role_priority.get(kind, 0)

            candidate = {
                "player": player,
                "playerId": player_id,
                "team": team,
                "kind": kind,
                "score": score,
            }

            existing = best_by_player_team.get(key)
            if not existing or candidate["score"] > existing.get("score", 0):
                best_by_player_team[key] = candidate

    matches = list(best_by_player_team.values())

    # Also support professional team/matchup search from the same box.
    # This keeps the UI streamlined: one search input can load either player props or team/game props.
    if len(target) >= 2:
        matches.extend(search_matchups(season, "", query, limit=limit))
        team_query = norm_team(query)
        if team_query in TEAM_ABBRS:
            matches.append({
                "player": team_query,
                "playerId": "",
                "team": team_query,
                "kind": "team",
                "role": "Team",
                "score": 85,
            })

    matches.sort(key=lambda item: (-item.get("score", 0), item.get("player", ""), item.get("team", "")))
    return matches[:limit]

def game_for_team(season: int, date_label: str, team: str) -> dict[str, str]:
    team = clean(team).upper()
    for game in games_for_date(season, date_label):
        home = clean(game.get("home")).upper()
        away = clean(game.get("away")).upper()
        if team in {home, away}:
            return game
    return {}


def game_for_probable_pitcher(season: int, date_label: str, player: str) -> tuple[dict[str, str], str]:
    target = norm(player)

    for game in games_for_date(season, date_label):
        home_pitcher = clean(game.get("homeProbablePitcher"))
        away_pitcher = clean(game.get("awayProbablePitcher"))

        if home_pitcher and norm(home_pitcher) == target:
            return game, clean(game.get("home")).upper()

        if away_pitcher and norm(away_pitcher) == target:
            return game, clean(game.get("away")).upper()

    return {}, ""


def infer_role(season: int, player: str) -> str:
    target = norm(player)

    for row in read_csv_rows(STATS_DIR / f"pitcher_totals_{season}.csv"):
        if norm(row.get("player")) == target:
            return "pitcher"

    for row in read_csv_rows(STATS_DIR / f"batter_totals_{season}.csv"):
        if norm(row.get("player")) == target:
            return "batter"

    return "batter"


def autofill_player(season: int, date_label: str, player: str, role: str = "auto") -> dict[str, Any]:
    player = clean(player)
    role = clean(role).lower() or "auto"

    if not player:
        return {"error": "player is required"}

    matchup_payload = autofill_matchup(season, date_label, player)
    if matchup_payload and (role in {"auto", "team", "matchup"} or norm_team(player) in TEAM_ABBRS or " vs " in player.lower() or "@" in player):
        return matchup_payload

    if role == "auto":
        role = infer_role(season, player)

    matches = find_player(season, player, limit=8)
    best = matches[0] if matches else {}
    player_name = clean(best.get("player")) or player

    game = {}
    team = ""

    if role == "pitcher":
        game, team = game_for_probable_pitcher(season, date_label, player_name)

    if not game:
        team = clean(best.get("team")).upper()
        if not team:
            team = player_team_from_logs(season, date_label, player_name, role)
        game = game_for_team(season, date_label, team)

    if not game:
        return {
            "season": season,
            "date": date_label,
            "player": player_name,
            "role": role,
            "matches": matches,
            "foundGame": False,
            "message": "No game found for this player/date. Check date, team, or whether the player was active that day.",
        }

    home = clean(game.get("home")).upper()
    away = clean(game.get("away")).upper()

    if not team:
        # If role is pitcher and probable pitcher matched, team may already be set.
        if norm(game.get("homeProbablePitcher")) == norm(player_name):
            team = home
        elif norm(game.get("awayProbablePitcher")) == norm(player_name):
            team = away

    opponent = away if team == home else home
    venue = clean(game.get("venue"))
    game_pk = clean(game.get("gamePk"))

    home_pitcher = clean(game.get("homeProbablePitcher"))
    away_pitcher = clean(game.get("awayProbablePitcher"))

    opposing_pitcher = ""
    team_pitcher = ""

    if team == home:
        team_pitcher = home_pitcher
        opposing_pitcher = away_pitcher
    elif team == away:
        team_pitcher = away_pitcher
        opposing_pitcher = home_pitcher

    if role == "pitcher":
        pitcher_field = player_name
        default_market = "pitcher_strikeouts"
        suggested_markets = [
            "pitcher_strikeouts",
            "pitcher_hits_allowed",
            "pitcher_earned_runs",
        ]
    else:
        pitcher_field = opposing_pitcher
        default_market = "batter_total_bases"
        suggested_markets = [
            "batter_total_bases",
            "batter_hits",
            "batter_home_runs",
        ]

    return {
        "season": season,
        "date": date_label,
        "player": player_name,
        "playerId": clean(best.get("playerId")),
        "role": role,
        "team": team,
        "opponent": opponent,
        "pitcher": pitcher_field,
        "opposingPitcher": opposing_pitcher,
        "teamPitcher": team_pitcher,
        "home": home,
        "away": away,
        "venue": venue,
        "gamePk": game_pk,
        "gameDate": clean(game.get("gameDate")),
        "foundGame": True,
        "defaultMarket": default_market,
        "suggestedMarkets": suggested_markets,
        "matches": matches,
        "summary": f"{player_name} - {away} @ {home}" + (f", {venue}" if venue else ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Player autocomplete/autofill helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search")
    search.add_argument("--season", type=int, default=2026)
    search.add_argument("--q", required=True)
    search.add_argument("--limit", type=int, default=10)

    fill = sub.add_parser("autofill")
    fill.add_argument("--season", type=int, default=2026)
    fill.add_argument("--date", required=True)
    fill.add_argument("--player", required=True)
    fill.add_argument("--role", default="auto")

    args = parser.parse_args()

    if args.command == "search":
        print(json.dumps(find_player(args.season, args.q, args.limit), indent=2))
    elif args.command == "autofill":
        print(json.dumps(autofill_player(args.season, args.date, args.player, args.role), indent=2))


if __name__ == "__main__":
    main()
