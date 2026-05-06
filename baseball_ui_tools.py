
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ODDSPAPI_DIR = DATA_DIR / "cache" / "oddspapi"
WEATHER_DIR = DATA_DIR / "cache" / "weather"
UMPIRE_DIR = DATA_DIR / "cache" / "umpires"
ODDS_MOVEMENT_DIR = DATA_DIR / "cache" / "odds_movement"

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


def latest_game_market_files() -> list[Path]:
    if not ODDSPAPI_DIR.exists():
        return []
    return sorted(ODDSPAPI_DIR.glob("historical_game_markets_pregame_latest_*.csv"))


def load_game_market_rows(date_label: str = "", season: int = 2026) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    sources: list[str] = []
    for path in latest_game_market_files():
        file_rows = read_csv(path)
        if not file_rows:
            continue
        if date_label:
            file_rows = [row for row in file_rows if clean(row.get("date"))[:10] == date_label]
        elif season:
            file_rows = [row for row in file_rows if clean(row.get("date")).startswith(str(season))]
        if file_rows:
            sources.append(str(path))
            rows.extend(file_rows)
    return rows, sources


def load_weather_rows(season: int) -> list[dict[str, str]]:
    return read_csv(WEATHER_DIR / f"weather_features_{season}.csv")


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
        clean(row.get("team")).upper(),
        clean(row.get("opponent")).upper(),
    )


def game_key(row: dict[str, str]) -> tuple[str, str]:
    return (clean(row.get("fixtureId")), clean(row.get("date"))[:10])


def summarize_moneyline(rows: list[dict[str, str]]) -> dict[str, Any]:
    moneyline = [row for row in rows if clean(row.get("market")) == "moneyline" and clean(row.get("team"))]
    by_team: dict[str, list[float]] = defaultdict(list)
    by_team_books: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in moneyline:
        odds = to_float(row.get("americanOdds"))
        if odds is None:
            continue
        team = clean(row.get("team")).upper()
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
            "team": clean(row.get("team")).upper(),
            "opponent": clean(row.get("opponent")).upper(),
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
    team_filter = clean(query.get("team", [""])[0]).upper()
    limit = int(query.get("limit", ["100"])[0])

    rows, sources = load_game_market_rows(date_label, season)
    if team_filter:
        rows = [row for row in rows if team_filter in {clean(row.get("team")).upper(), clean(row.get("opponent")).upper()}]

    games: dict[tuple[str, str], dict[str, Any]] = {}
    rows_by_game: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = game_key(row)
        rows_by_game[key].append(row)
        game = games.setdefault(key, {
            "fixtureId": key[0],
            "date": key[1],
            "startTime": clean(row.get("startTime")),
            "teams": sorted({clean(row.get("team")).upper(), clean(row.get("opponent")).upper()} - {""}),
            "marketsAvailable": set(),
        })
        game["marketsAvailable"].add(clean(row.get("market")))
        for value in [clean(row.get("team")).upper(), clean(row.get("opponent")).upper()]:
            if value and value not in game["teams"]:
                game["teams"].append(value)

    weather_by_date_team = {(clean(row.get("date"))[:10], clean(row.get("team")).upper()): row for row in load_weather_rows(season)}
    umpire_by_date_game = {(clean(row.get("date"))[:10], clean(row.get("gamePk"))): row for row in load_umpire_rows(season)}

    out_games = []
    for key, game in games.items():
        game_rows = rows_by_game[key]
        moneyline = summarize_moneyline(game_rows)
        game["marketsAvailable"] = sorted([m for m in game["marketsAvailable"] if m])
        game["moneyline"] = moneyline
        game["runLines"] = summarize_line(game_rows, "run_line")[:12]
        game["gameTotals"] = summarize_line(game_rows, "game_total_runs")[:12]
        game["firstInningTotals"] = summarize_line(game_rows, "first_inning_total_runs")[:12]
        game["teamTotals"] = summarize_line(game_rows, "team_total_runs")[:16]
        game["lineupStatus"] = {
            "available": False,
            "note": "Projected/confirmed lineup integration is future-ready. Endpoint currently exposes game, weather, umpire, and market context.",
        }
        game["weather"] = [compact_row({
            "team": team,
            "temperature": weather_by_date_team.get((game["date"], team), {}).get("temperature"),
            "windMph": weather_by_date_team.get((game["date"], team), {}).get("wind_mph"),
            "roof": weather_by_date_team.get((game["date"], team), {}).get("roof"),
            "venue": weather_by_date_team.get((game["date"], team), {}).get("venue"),
        }) for team in game.get("teams", [])]
        game["umpire"] = compact_row(umpire_by_date_game.get((game["date"], clean(game.get("fixtureId"))), {}))
        out_games.append(game)

    out_games.sort(key=lambda item: (item.get("startTime") or "", item.get("fixtureId") or ""))
    return {
        "ok": True,
        "season": season,
        "date": date_label,
        "games": out_games[:limit],
        "gameCount": len(out_games),
        "sourceFiles": sources,
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
            "team": clean(row.get("team")).upper(),
            "opponent": clean(row.get("opponent")).upper(),
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
            "team": clean(row.get("team")).upper(),
            "opponent": clean(row.get("opponent")).upper(),
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
            "team": clean(row.get("team")).upper(),
            "opponent": clean(row.get("opponent")).upper(),
            "bookmaker": clean(row.get("bookmaker")),
            "line": to_float(row.get("line")),
            "americanOdds": to_int(row.get("americanOdds")),
            "date": clean(row.get("date"))[:10],
        }))
        if len(results) >= limit:
            break

    return {"ok": True, "season": season, "date": date_label, "query": q, "results": results, "resultCount": len(results), "sourceFiles": sources}
