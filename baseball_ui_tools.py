
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ODDSPAPI_DIR = DATA_DIR / "cache" / "oddspapi"
WEATHER_DIR = DATA_DIR / "cache" / "weather"
UMPIRE_DIR = DATA_DIR / "cache" / "umpires"
ODDS_MOVEMENT_DIR = DATA_DIR / "cache" / "odds_movement"
INCREMENTAL_STATS_DIR = DATA_DIR / "cache" / "incremental_stats"
CLOUD_SUMMARIES_DIR = DATA_DIR / "cloud" / "summaries"
IMPORTS_DIR = DATA_DIR / "imports"

TEAM_NORM = {
    "SFG": "SF", "CWS": "CHW", "KCR": "KC", "TBR": "TB",
    "SDP": "SD", "WSN": "WSH", "SLN": "STL", "CHN": "CHC",
    "ANA": "LAA", "MON": "WSH", "OAK": "ATH",
}

GAME_MARKETS = {
    "moneyline",
    "moneyline_first_five",
    "run_line",
    "run_line_first_five",
    "run_line_first_inning",
    "game_total_runs",
    "first_five_total_runs",
    "first_inning_total_runs",
    "team_total_runs",
    "team_first_to_score",
}

TEAM_PROP_MARKETS = {
    "moneyline",
    "run_line",
    "run_line_first_inning",
    "game_total_runs",
    "team_total_runs",
    "first_inning_total_runs",
    "first_five_total_runs",
    "run_line_first_five",
    "moneyline_first_five",
    "team_first_to_score",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_team(value: Any) -> str:
    team = clean(value).upper()
    return TEAM_NORM.get(team, team)


def to_float(value: Any, default: float | None = None) -> float | None:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def to_int(value: Any, default: int | None = None) -> int | None:
    number = to_float(value)
    if number is None:
        return default
    return int(number)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def norm_name(value: Any) -> str:
    return " ".join(clean(value).lower().replace(".", "").replace(",", "").split())


def safe_date(value: Any, fallback: date | None = None) -> date | None:
    text = clean(value)[:10]
    if not text:
        return fallback
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return fallback


def innings_to_float(value: Any) -> float:
    """Parse MLB innings strings. Game logs often use 6.1/6.2 for thirds."""
    text = clean(value)
    if not text:
        return 0.0
    if "." in text:
        whole, frac = text.split(".", 1)
        if frac in {"1", "2"}:
            return to_float(whole, 0.0) + (1.0 / 3.0 if frac == "1" else 2.0 / 3.0)
    return to_float(text, 0.0) or 0.0


def load_summary_games(date_label: str) -> list[dict[str, Any]]:
    path = CLOUD_SUMMARIES_DIR / f"games_{date_label}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        games = payload.get("games") or payload.get("data") or []
        return [item for item in games if isinstance(item, dict)]
    return []


def match_summary_game(game: dict[str, Any], game_rows: list[dict[str, str]], summaries: list[dict[str, Any]]) -> dict[str, Any]:
    fixture_id = clean(game.get("fixtureId"))
    teams = {clean(team).upper() for team in game.get("teams", []) if clean(team)}
    for row in game_rows:
        teams.update({clean(row.get("team")).upper(), clean(row.get("opponent")).upper()})
    teams.discard("")

    for item in summaries:
        if fixture_id and fixture_id == clean(item.get("gamePk")):
            return item
    for item in summaries:
        pair = {clean(item.get("away")).upper(), clean(item.get("home")).upper()}
        if teams and teams == pair:
            return item
    for item in summaries:
        pair = {clean(item.get("away")).upper(), clean(item.get("home")).upper()}
        if teams and teams.issubset(pair):
            return item
    return {}


def pitch_count(row: dict[str, Any]) -> int:
    return to_int(row.get("pitchesThrown") or row.get("pitches") or row.get("pitchCount"), 0) or 0


def pitcher_totals_index(season: int) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv(INCREMENTAL_STATS_DIR / f"pitcher_totals_{season}.csv")
    return {
        (norm_name(row.get("player")), clean(row.get("team")).upper()): row
        for row in rows
        if clean(row.get("player")) and clean(row.get("team"))
    }


def bullpen_pitchers_payload(season: int, team: str, starting_pitcher: str, as_of_date: str) -> list[dict[str, Any]]:
    """Return recent bullpen workload without failing the parent endpoint.

    The current cache does not explicitly mark reliever roles, so we infer the
    bullpen from recent pitcher game logs: exclude the listed starter and prefer
    pitchers averaging <= 3.25 IP per appearance. If that heuristic finds no
    rows for a team, fall back to every non-starter pitcher for visibility.
    """
    team = clean(team).upper()
    if not team:
        return []

    logs_path = INCREMENTAL_STATS_DIR / f"pitcher_game_logs_{season}.csv"
    logs = read_csv(logs_path)
    if not logs:
        return []

    as_of = safe_date(as_of_date, datetime.now().date()) or datetime.now().date()
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    starter_norm = norm_name(starting_pitcher)

    for row in logs:
        if clean(row.get("team")).upper() != team:
            continue
        player = clean(row.get("player"))
        if not player or norm_name(player) == starter_norm:
            continue
        row_date = safe_date(row.get("date"))
        if row_date and row_date > as_of:
            continue
        grouped[player].append(row)

    if not grouped:
        return []

    totals = pitcher_totals_index(season)
    candidates: list[tuple[str, list[dict[str, str]], float]] = []
    for player, player_logs in grouped.items():
        player_logs.sort(key=lambda item: (clean(item.get("date")), clean(item.get("gamePk"))))
        total_ip = sum(innings_to_float(item.get("inningsPitched")) for item in player_logs)
        avg_ip = total_ip / len(player_logs) if player_logs else 0.0
        candidates.append((player, player_logs, avg_ip))

    relievers = [(p, rows, avg_ip) for p, rows, avg_ip in candidates if avg_ip <= 3.25]
    if not relievers:
        relievers = candidates

    output: list[dict[str, Any]] = []
    for player, player_logs, avg_ip in relievers:
        recent = sorted(player_logs, key=lambda item: (clean(item.get("date")), clean(item.get("gamePk"))))
        last = recent[-1] if recent else {}
        last_date = safe_date(last.get("date"))
        total_row = totals.get((norm_name(player), team), {})
        pitch_ytd = to_int(total_row.get("pitchesThrown"), None)
        if pitch_ytd is None:
            pitch_ytd = sum(pitch_count(item) for item in recent)
        batters_faced = to_float(total_row.get("battersFaced"), 0.0) or sum(to_float(item.get("battersFaced"), 0.0) for item in recent)
        strikeouts = to_float(total_row.get("strikeouts"), 0.0) or sum(to_float(item.get("strikeOuts"), 0.0) for item in recent)
        era = to_float(total_row.get("era"), None)
        if era is None:
            ip = sum(innings_to_float(item.get("inningsPitched")) for item in recent)
            er = sum(to_float(item.get("earnedRuns"), 0.0) for item in recent)
            era = round((er * 9.0) / ip, 2) if ip else None
        k_pct = to_float(total_row.get("kRate"), None)
        if k_pct is None:
            k_pct = round((strikeouts / batters_faced) * 100, 1) if batters_faced else None

        output.append(compact_row({
            "name": player,
            "team": team,
            "pitchCountYTD": pitch_ytd,
            "pitchCountL3": sum(pitch_count(item) for item in recent[-3:]),
            "pitchCountL5": sum(pitch_count(item) for item in recent[-5:]),
            "daysRest": (as_of - last_date).days if last_date else None,
            "lastAppearance": last_date.isoformat() if last_date else "",
            "appearances": len(recent),
            "avgInningsPerAppearance": round(avg_ip, 2),
            "era": round(era, 2) if era is not None else None,
            "kPct": round(k_pct, 1) if k_pct is not None else None,
        }))

    output.sort(key=lambda item: (-(to_int(item.get("pitchCountL5"), 0) or 0), to_int(item.get("daysRest"), 99) or 99, clean(item.get("name"))))
    return output[:10]


def pitcher_season_stats(season: int, team: str, pitcher_name: str) -> dict[str, Any]:
    team = normalize_team(team)
    pitcher_norm = norm_name(pitcher_name)
    if not team or not pitcher_norm:
        return {}

    totals = read_csv(INCREMENTAL_STATS_DIR / f"pitcher_totals_{season}.csv")
    total_row = next(
        (row for row in totals if norm_name(row.get("player")) == pitcher_norm and normalize_team(row.get("team")) == team),
        {},
    )

    logs = [
        row for row in read_csv(INCREMENTAL_STATS_DIR / f"pitcher_game_logs_{season}.csv")
        if norm_name(row.get("player")) == pitcher_norm and normalize_team(row.get("team")) == team
    ]

    wins = sum(to_int(row.get("wins"), 0) or 0 for row in logs)
    losses = sum(to_int(row.get("losses"), 0) or 0 for row in logs)
    ip = to_float(total_row.get("ip"), None)
    if ip is None and logs:
        ip = sum(innings_to_float(row.get("inningsPitched")) for row in logs)

    hits_allowed = to_float(total_row.get("hitsAllowed"), None)
    if hits_allowed is None and logs:
        hits_allowed = sum(to_float(row.get("hits"), 0.0) or 0.0 for row in logs)
    h9 = to_float(total_row.get("hitsPer9") or total_row.get("hPer9"), None)
    if h9 is None and ip:
        h9 = (hits_allowed or 0.0) * 9.0 / ip

    return compact_row({
        "record": f"{wins}-{losses}" if logs else "",
        "era": to_float(total_row.get("era"), None),
        "ip": round(ip, 1) if ip is not None else None,
        "h9": round(h9, 2) if h9 is not None else None,
        "k9": to_float(total_row.get("kPer9"), None),
        "bb9": to_float(total_row.get("bbPer9"), None),
        "whip": to_float(total_row.get("whip"), None),
        "games": to_int(total_row.get("games"), None),
    })


def team_side_payload(side: str, team: str, summary: dict[str, Any], season: int, date_label: str) -> dict[str, Any]:
    team = normalize_team(team)
    pitcher_key = "homeProbablePitcher" if side == "home" else "awayProbablePitcher"
    name_key = "homeName" if side == "home" else "awayName"
    probable_pitcher = clean(summary.get(pitcher_key))
    return compact_row({
        "side": side,
        "team": team,
        "teamName": clean(summary.get(name_key)),
        "probablePitcher": probable_pitcher,
        "pitcherSeasonStats": pitcher_season_stats(season, team, probable_pitcher),
        "bullpenPitchers": bullpen_pitchers_payload(season, team, probable_pitcher, date_label),
    })


def lineup_stats_from_total(row: dict[str, str]) -> dict[str, Any]:
    return compact_row({
        "ab": to_int(row.get("ab"), 0),
        "pa": to_int(row.get("pa"), 0),
        "avg": to_float(row.get("avg"), None),
        "hr": to_int(row.get("homeRuns"), 0),
        "homeRuns": to_int(row.get("homeRuns"), 0),
        "rbi": to_int(row.get("rbi"), 0),
        "ops": to_float(row.get("ops_est") or row.get("ops"), None),
        "kPct": to_float(row.get("kRate"), None),
        "bbPct": to_float(row.get("bbRate"), None),
        "hits": to_int(row.get("hits"), 0),
        "totalBases": to_int(row.get("totalBases"), 0),
    })


def projected_lineup_from_summary(date_label: str, team: str, opponent: str = "", game_pk: str = "") -> list[dict[str, Any]]:
    """Best-effort parser for future game-summary lineups.

    Existing MVP summary files are a list of games and do not include lineups,
    but this supports both per-game `lineups` objects and top-level `lineups`
    dictionaries for forward compatibility.
    """
    path = CLOUD_SUMMARIES_DIR / f"games_{date_label}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []

    team = clean(team).upper()
    opponent = clean(opponent).upper()

    def game_matches(game: dict[str, Any]) -> bool:
        if game_pk and clean(game.get("gamePk")) == clean(game_pk):
            return True
        pair = {clean(game.get("home")).upper(), clean(game.get("away")).upper()}
        return bool(team and team in pair and (not opponent or opponent in pair))

    candidate: Any = None
    if isinstance(payload, dict):
        lineups = payload.get("lineups")
        if isinstance(lineups, dict):
            candidate = lineups.get(team) or lineups.get(team.lower())
        elif isinstance(lineups, list):
            for item in lineups:
                if isinstance(item, dict) and clean(item.get("team")).upper() == team:
                    candidate = item.get("players") or item.get("lineup") or item
                    break
        games = payload.get("games") or []
    elif isinstance(payload, list):
        games = payload
    else:
        games = []

    if candidate is None:
        for game in games:
            if not isinstance(game, dict) or not game_matches(game):
                continue
            lineups = game.get("lineups") or game.get("lineup") or {}
            if isinstance(lineups, dict):
                candidate = lineups.get(team) or lineups.get("home" if clean(game.get("home")).upper() == team else "away")
            elif isinstance(lineups, list):
                for item in lineups:
                    if isinstance(item, dict) and clean(item.get("team")).upper() == team:
                        candidate = item.get("players") or item.get("lineup") or item
                        break
            break

    players = candidate.get("players") if isinstance(candidate, dict) else candidate
    if not isinstance(players, list):
        return []

    output = []
    for index, item in enumerate(players[:9], start=1):
        if isinstance(item, str):
            output.append({"battingOrder": index, "player": item, "position": "", "hand": "", "stats": {}})
        elif isinstance(item, dict):
            output.append(compact_row({
                "battingOrder": to_int(item.get("battingOrder") or item.get("order"), index),
                "player": clean(item.get("player") or item.get("name") or item.get("fullName")),
                "position": clean(item.get("position") or item.get("pos")),
                "hand": clean(item.get("hand") or item.get("bats") or item.get("batSide")),
                "stats": item.get("stats") if isinstance(item.get("stats"), dict) else {},
            }))
    return [item for item in output if clean(item.get("player"))]


def lineup_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = int(query.get("season", ["2026"])[0])
    date_label = clean(query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0])
    team = normalize_team(query.get("team", [""])[0])
    opponent = clean(query.get("opponent", [""])[0]).upper()
    game_pk = clean(query.get("gamePk", query.get("fixtureId", [""]))[0])

    if not team:
        return {"ok": False, "error": "team is required", "lineup": [], "source": "missing_team"}

    projected = projected_lineup_from_summary(date_label, team, opponent, game_pk)
    if projected:
        return {
            "ok": True,
            "season": season,
            "date": date_label,
            "team": team,
            "opponent": opponent,
            "gamePk": game_pk,
            "source": "projected",
            "lineup": projected,
            "lineupCount": len(projected),
        }

    totals = [
        row for row in read_csv(INCREMENTAL_STATS_DIR / f"batter_totals_{season}.csv")
        if clean(row.get("team")).upper() == team
    ]
    totals.sort(key=lambda row: (to_float(row.get("ab"), 0.0) or 0.0, to_float(row.get("pa"), 0.0) or 0.0), reverse=True)
    lineup = []
    for index, row in enumerate(totals[:9], start=1):
        lineup.append({
            "battingOrder": index,
            "playerId": clean(row.get("playerId")),
            "player": clean(row.get("player")),
            "position": "",
            "hand": "",
            "stats": lineup_stats_from_total(row),
        })

    return {
        "ok": True,
        "season": season,
        "date": date_label,
        "team": team,
        "opponent": opponent,
        "gamePk": game_pk,
        "source": "estimated_by_pa",
        "lineup": lineup,
        "lineupCount": len(lineup),
        "note": "Projected lineups were not present in the summary file; using the top 9 batters by AB/PA as an MVP fallback.",
    }


def latest_game_market_files() -> list[Path]:
    files: list[Path] = []
    if ODDSPAPI_DIR.exists():
        files.extend(ODDSPAPI_DIR.glob("historical_game_markets_pregame_latest_*.csv"))
        files.extend(ODDSPAPI_DIR.glob("historical_game_markets_pregame_latest_*_season*.csv"))
    if ODDS_MOVEMENT_DIR.exists():
        files.extend(ODDS_MOVEMENT_DIR.glob("prop_snapshots_*.csv"))
    if IMPORTS_DIR.exists():
        files.extend(IMPORTS_DIR.glob("game_odds_template_*.csv"))
    return sorted(set(files))


def _market_row(base: dict[str, str], market: str, team: str, opponent: str, odds: Any = "", line: Any = "", outcome: str = "", book: str = "Manual") -> dict[str, str]:
    return {
        "fixtureId": clean(base.get("fixtureId") or base.get("gamePk")),
        "date": clean(base.get("date"))[:10],
        "startTime": clean(base.get("startTime") or base.get("gameDate")),
        "market": market,
        "team": normalize_team(team),
        "opponent": normalize_team(opponent),
        "line": clean(line),
        "outcomeName": outcome,
        "americanOdds": clean(odds),
        "bookmaker": clean(base.get("bookmaker") or base.get("sportsbook") or book),
        "createdAt": clean(base.get("createdAt") or base.get("snapshotAt")),
    }


def rows_from_game_odds_template(row: dict[str, str]) -> list[dict[str, str]]:
    team = normalize_team(row.get("team"))
    opponent = normalize_team(row.get("opponent"))
    if not team or not opponent:
        return []
    output: list[dict[str, str]] = []
    team_ml = clean(row.get("team_moneyline") or row.get("close_team_moneyline"))
    opponent_ml = clean(row.get("opponent_moneyline"))
    if team_ml:
        output.append(_market_row(row, "moneyline", team, opponent, team_ml, "", team))
    if opponent_ml:
        output.append(_market_row(row, "moneyline", opponent, team, opponent_ml, "", opponent))
    total = clean(row.get("game_total") or row.get("close_game_total"))
    if total:
        over_odds = clean(row.get("over_odds") or row.get("game_total_over_odds") or row.get("total_over_odds") or "-110")
        under_odds = clean(row.get("under_odds") or row.get("game_total_under_odds") or row.get("total_under_odds") or "-110")
        output.append(_market_row(row, "game_total_runs", team, opponent, over_odds, total, "Over"))
        output.append(_market_row(row, "game_total_runs", team, opponent, under_odds, total, "Under"))
    return output


def normalize_game_market_file_rows(path: Path, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if path.name.startswith("game_odds_template_"):
        output: list[dict[str, str]] = []
        for row in rows:
            output.extend(rows_from_game_odds_template(row))
        return output

    output = []
    for row in rows:
        market = clean(row.get("market"))
        if market in {"h2h", "money_line", "ml"}:
            market = "moneyline"
        elif market in {"spreads", "spread"}:
            market = "run_line"
        elif market in {"totals", "total"}:
            market = "game_total_runs"
        if market not in GAME_MARKETS:
            continue
        item = dict(row)
        item["market"] = market
        item["team"] = normalize_team(item.get("team"))
        item["opponent"] = normalize_team(item.get("opponent"))
        if "bookmaker" not in item and "sportsbook" in item:
            item["bookmaker"] = item.get("sportsbook", "")
        if "createdAt" not in item and "snapshotAt" in item:
            item["createdAt"] = item.get("snapshotAt", "")
        output.append(item)
    return output


def load_game_market_rows(date_label: str = "", season: int = 2026) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    sources: list[str] = []
    for path in latest_game_market_files():
        file_rows = normalize_game_market_file_rows(path, read_csv(path))
        if not file_rows:
            continue
        if date_label:
            file_rows = [row for row in file_rows if clean(row.get("date"))[:10] == date_label]
        elif season:
            file_rows = [row for row in file_rows if clean(row.get("date")).startswith(str(season)) or clean(row.get("season")) == str(season)]
        if file_rows:
            sources.append(str(path))
            rows.extend(file_rows)
    return rows, sources


def load_weather_rows(season: int) -> list[dict[str, str]]:
    rows = read_csv(WEATHER_DIR / f"weather_features_{season}.csv")
    rows.extend(read_csv(WEATHER_DIR / f"game_weather_{season}.csv"))
    return rows


def load_umpire_rows(season: int) -> list[dict[str, str]]:
    return read_csv(UMPIRE_DIR / f"game_umpires_{season}.csv")


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "")}


def market_label(market: str) -> str:
    return market.replace("_", " ").title()


def implied_probability(american_odds: Any) -> float | None:
    odds = to_float(american_odds)
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return round(100 / (odds + 100), 4)
    return round(abs(odds) / (abs(odds) + 100), 4)


def group_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        clean(row.get("fixtureId")),
        clean(row.get("date"))[:10],
        normalize_team(row.get("team")),
        normalize_team(row.get("opponent")),
    )


def game_key(row: dict[str, str]) -> tuple[str, str]:
    fixture = clean(row.get("fixtureId"))
    date_label = clean(row.get("date"))[:10]
    if fixture:
        return (fixture, date_label)
    teams = sorted({normalize_team(row.get("team")), normalize_team(row.get("opponent"))} - {""})
    return ("-".join(teams), date_label)


def summarize_moneyline(rows: list[dict[str, str]]) -> dict[str, Any]:
    moneyline = [row for row in rows if clean(row.get("market")) == "moneyline" and clean(row.get("team"))]
    by_team: dict[str, list[float]] = defaultdict(list)
    by_team_books: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in moneyline:
        odds = to_float(row.get("americanOdds"))
        if odds is None:
            continue
        team = normalize_team(row.get("team"))
        by_team[team].append(odds)
        by_team_books[team].append({
            "bookmaker": clean(row.get("bookmaker")),
            "americanOdds": int(odds),
            "impliedProbability": implied_probability(odds),
        })
    teams = []
    for team, odds_list in by_team.items():
        avg = sum(odds_list) / len(odds_list)
        teams.append({
            "team": team,
            "avgAmericanOdds": round(avg),
            "avgImpliedProbability": implied_probability(avg),
            "books": by_team_books[team],
        })
    teams.sort(key=lambda item: item.get("avgImpliedProbability") or 0, reverse=True)
    favorite = teams[0] if teams else {}
    underdog = teams[-1] if len(teams) > 1 else {}
    return {"teams": teams, "favorite": favorite, "underdog": underdog}


def summarize_line(rows: list[dict[str, str]], market: str) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if clean(row.get("market")) != market:
            continue
        out.append(compact_row({
            "bookmaker": clean(row.get("bookmaker")),
            "team": normalize_team(row.get("team")),
            "opponent": normalize_team(row.get("opponent")),
            "line": to_float(row.get("line")),
            "outcomeName": clean(row.get("outcomeName")),
            "americanOdds": to_int(row.get("americanOdds")),
            "impliedProbability": implied_probability(row.get("americanOdds")),
            "createdAt": clean(row.get("createdAt")),
        }))
    return out


def game_context_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = int(query.get("season", ["2026"])[0])
    date_label = clean(query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0])
    team_filter = normalize_team(query.get("team", [""])[0])
    limit = int(query.get("limit", ["100"])[0])

    rows, sources = load_game_market_rows(date_label, season)
    if team_filter:
        rows = [row for row in rows if team_filter in {normalize_team(row.get("team")), normalize_team(row.get("opponent"))}]

    summaries = load_summary_games(date_label)
    games: dict[tuple[str, str], dict[str, Any]] = {}
    rows_by_game: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        key = game_key(row)
        rows_by_game[key].append(row)
        game = games.setdefault(key, {
            "fixtureId": key[0],
            "date": key[1] or date_label,
            "startTime": clean(row.get("startTime")),
            "teams": sorted({clean(row.get("team")).upper(), clean(row.get("opponent")).upper()} - {""}),
            "marketsAvailable": set(),
        })
        game["marketsAvailable"].add(clean(row.get("market")))
        for value in [clean(row.get("team")).upper(), clean(row.get("opponent")).upper()]:
            if value and value not in game["teams"]:
                game["teams"].append(value)

    # If odds files are missing for the slate, still expose the schedule-backed
    # game context so Stage 7/8 screens can render instead of going blank.
    if not games and summaries:
        for item in summaries:
            away = normalize_team(item.get("away"))
            home = normalize_team(item.get("home"))
            if team_filter and team_filter not in {away, home}:
                continue
            key = (clean(item.get("gamePk")), date_label)
            games[key] = {
                "fixtureId": key[0],
                "date": date_label,
                "startTime": clean(item.get("gameDate")),
                "teams": [team for team in [away, home] if team],
                "marketsAvailable": set(),
            }
            rows_by_game[key] = []

    weather_by_date_team: dict[tuple[str, str], dict[str, str]] = {}
    for row in load_weather_rows(season):
        weather_date = clean(row.get("date"))[:10]
        for team_key in [row.get("team"), row.get("home"), row.get("away")]:
            team = normalize_team(team_key)
            if weather_date and team:
                weather_by_date_team[(weather_date, team)] = row
    umpire_by_date_game = {(clean(row.get("date"))[:10], clean(row.get("gamePk"))): row for row in load_umpire_rows(season)}

    out_games = []
    for key, game in games.items():
        game_rows = rows_by_game[key]
        summary = match_summary_game(game, game_rows, summaries)
        away_team = normalize_team(summary.get("away"))
        home_team = normalize_team(summary.get("home"))
        if not away_team or not home_team:
            teams = [normalize_team(team) for team in game.get("teams", []) if clean(team)]
            away_team = away_team or (teams[0] if teams else "")
            home_team = home_team or (teams[1] if len(teams) > 1 else "")

        if away_team or home_team:
            ordered_teams = [team for team in [away_team, home_team] if team]
            game["teams"] = ordered_teams

        moneyline = summarize_moneyline(game_rows)
        game["marketsAvailable"] = sorted([m for m in game["marketsAvailable"] if m])
        game["moneyline"] = moneyline
        game["runLines"] = summarize_line(game_rows, "run_line")[:12]
        game["gameTotals"] = summarize_line(game_rows, "game_total_runs")[:12]
        game["firstInningTotals"] = summarize_line(game_rows, "first_inning_total_runs")[:12]
        game["teamTotals"] = summarize_line(game_rows, "team_total_runs")[:16]
        game["summary"] = compact_row({
            "gamePk": clean(summary.get("gamePk")),
            "status": clean(summary.get("status")),
            "codedGameState": clean(summary.get("codedGameState")),
            "gameDate": clean(summary.get("gameDate")),
            "venue": clean(summary.get("venue")),
            "awayName": clean(summary.get("awayName")),
            "homeName": clean(summary.get("homeName")),
            "awayScore": summary.get("awayScore"),
            "homeScore": summary.get("homeScore"),
        })
        game["away"] = team_side_payload("away", away_team, summary, season, game["date"])
        game["home"] = team_side_payload("home", home_team, summary, season, game["date"])
        game["startingPitchers"] = {
            "away": compact_row({
                "team": away_team,
                "name": clean(summary.get("awayProbablePitcher")),
            }),
            "home": compact_row({
                "team": home_team,
                "name": clean(summary.get("homeProbablePitcher")),
            }),
        }
        game["lineupStatus"] = {
            "available": bool(projected_lineup_from_summary(game["date"], away_team, home_team, clean(summary.get("gamePk"))) or projected_lineup_from_summary(game["date"], home_team, away_team, clean(summary.get("gamePk")))),
            "endpoint": "/api/game/lineup",
            "note": "Projected lineups are used when present; otherwise /api/game/lineup falls back to top batters by AB/PA.",
        }
        weather_items = []
        for team in game.get("teams", []):
            weather_row = weather_by_date_team.get((game["date"], normalize_team(team)), {})
            weather_items.append(compact_row({
                "team": normalize_team(team),
                "temperatureF": weather_row.get("temperatureF") or weather_row.get("temperature"),
                "temperature": weather_row.get("temperatureF") or weather_row.get("temperature"),
                "windMph": weather_row.get("windMph") or weather_row.get("wind_mph"),
                "windDirection": weather_row.get("windDirection") or weather_row.get("wind_dir"),
                "roof": weather_row.get("roof"),
                "venue": weather_row.get("venue") or clean(summary.get("venue")),
                "weatherSummary": weather_row.get("weatherSummary"),
            }))
        game["weather"] = weather_items
        game["umpire"] = compact_row(umpire_by_date_game.get((game["date"], clean(game.get("fixtureId"))), {}))
        out_games.append(game)

    out_games.sort(key=lambda item: (item.get("startTime") or item.get("summary", {}).get("gameDate") or "", item.get("fixtureId") or ""))
    return {
        "ok": True,
        "season": season,
        "date": date_label,
        "games": out_games[:limit],
        "gameCount": len(out_games),
        "sourceFiles": sources,
        "summaryFiles": [str(CLOUD_SUMMARIES_DIR / f"games_{date_label}.json")] if summaries else [],
    }


def odds_market_signals_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = int(query.get("season", ["2026"])[0])
    date_label = clean(query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0])
    market = clean(query.get("market", [""])[0])
    team = clean(query.get("team", [""])[0]).upper()
    bookmaker = clean(query.get("bookmaker", [""])[0]).lower()
    limit = int(query.get("limit", ["250"])[0])

    rows, sources = load_game_market_rows(date_label, season)
    rows = [row for row in rows if clean(row.get("market")) in GAME_MARKETS]
    if market:
        rows = [row for row in rows if clean(row.get("market")) == market]
    if team:
        rows = [row for row in rows if team in {clean(row.get("team")).upper(), clean(row.get("opponent")).upper()}]
    if bookmaker:
        rows = [row for row in rows if clean(row.get("bookmaker")).lower() == bookmaker]

    normalized = []
    for row in rows[:limit]:
        normalized.append(compact_row({
            "fixtureId": clean(row.get("fixtureId")),
            "date": clean(row.get("date"))[:10],
            "startTime": clean(row.get("startTime")),
            "bookmaker": clean(row.get("bookmaker")),
            "market": clean(row.get("market")),
            "marketLabel": market_label(clean(row.get("market"))),
            "team": normalize_team(row.get("team")),
            "opponent": normalize_team(row.get("opponent")),
            "line": to_float(row.get("line")),
            "outcomeName": clean(row.get("outcomeName")),
            "americanOdds": to_int(row.get("americanOdds")),
            "impliedProbability": implied_probability(row.get("americanOdds")),
            "createdAt": clean(row.get("createdAt")),
        }))

    counts = defaultdict(int)
    books = defaultdict(int)
    for row in rows:
        counts[clean(row.get("market"))] += 1
        books[clean(row.get("bookmaker"))] += 1

    return {
        "ok": True,
        "season": season,
        "date": date_label,
        "filters": {"market": market, "team": team, "bookmaker": bookmaker},
        "rows": normalized,
        "rowCount": len(rows),
        "returnedRows": len(normalized),
        "marketCounts": dict(sorted(counts.items())),
        "bookmakerCounts": dict(sorted(books.items())),
        "sourceFiles": sources,
    }


def team_props_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = int(query.get("season", ["2026"])[0])
    date_label = clean(query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0])
    market = clean(query.get("market", [""])[0])
    q = clean(query.get("q", [""])[0]).upper()
    limit = int(query.get("limit", ["200"])[0])

    rows, sources = load_game_market_rows(date_label, season)
    rows = [row for row in rows if clean(row.get("market")) in TEAM_PROP_MARKETS]
    if market:
        rows = [row for row in rows if clean(row.get("market")) == market]
    if q:
        rows = [row for row in rows if q in f"{clean(row.get('team')).upper()} {clean(row.get('opponent')).upper()} {clean(row.get('market')).upper()} {clean(row.get('bookmaker')).upper()}"]

    out = []
    for row in rows[:limit]:
        out.append(compact_row({
            "fixtureId": clean(row.get("fixtureId")),
            "date": clean(row.get("date"))[:10],
            "bookmaker": clean(row.get("bookmaker")),
            "market": clean(row.get("market")),
            "marketLabel": market_label(clean(row.get("market"))),
            "team": normalize_team(row.get("team")),
            "opponent": normalize_team(row.get("opponent")),
            "line": to_float(row.get("line")),
            "outcomeName": clean(row.get("outcomeName")),
            "americanOdds": to_int(row.get("americanOdds")),
            "impliedProbability": implied_probability(row.get("americanOdds")),
            "createdAt": clean(row.get("createdAt")),
        }))

    counts = defaultdict(int)
    for row in rows:
        counts[clean(row.get("market"))] += 1
    return {"ok": True, "season": season, "date": date_label, "rows": out, "rowCount": len(rows), "returnedRows": len(out), "marketCounts": dict(sorted(counts.items())), "sourceFiles": sources}


def expanded_prop_search_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = int(query.get("season", ["2026"])[0])
    date_label = clean(query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0])
    q = clean(query.get("q", [""])[0]).lower()
    limit = int(query.get("limit", ["50"])[0])

    rows, sources = load_game_market_rows(date_label, season)
    results = []
    for row in rows:
        haystack = " ".join([
            clean(row.get("market")), clean(row.get("bookmaker")), clean(row.get("team")), clean(row.get("opponent")), clean(row.get("outcomeName")), clean(row.get("line")),
        ]).lower()
        if q and q not in haystack:
            continue
        results.append(compact_row({
            "type": "game_market",
            "label": f"{clean(row.get('market')).replace('_',' ')} {clean(row.get('team')) or clean(row.get('outcomeName'))} {clean(row.get('line'))} {clean(row.get('bookmaker'))}",
            "market": clean(row.get("market")),
            "team": normalize_team(row.get("team")),
            "opponent": normalize_team(row.get("opponent")),
            "bookmaker": clean(row.get("bookmaker")),
            "line": to_float(row.get("line")),
            "americanOdds": to_int(row.get("americanOdds")),
            "date": clean(row.get("date"))[:10],
        }))
        if len(results) >= limit:
            break

    return {"ok": True, "season": season, "date": date_label, "query": q, "results": results, "resultCount": len(results), "sourceFiles": sources}
