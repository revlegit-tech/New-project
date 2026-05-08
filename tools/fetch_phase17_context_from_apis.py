#!/usr/bin/env python3
"""Fetch/enrich Phase 17 game context from public/provider APIs.

This script intentionally avoids silent fallbacks:
- MLB schedule/venue context comes from the public MLB Stats API.
- Weather comes from Open-Meteo when venue coordinates are available.
- Game-line odds prefer PropLine's game-line endpoint when PROPLINE_API_KEY is set.
- The Odds API remains optional as a fallback/explicit source.
- Park factor comes from an explicit local venue reference table; unknown venues remain blank.

It enriches data/playerboard/playerboard_<season>.csv for a requested slate date.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE_DIR = PROJECT_ROOT / "data" / "warehouse" / "game_context"
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"

ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_VENUE_URL = "https://statsapi.mlb.com/api/v1/venues/{venue_id}"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Explicit reference values only. If a venue is not present, leave park_factor blank.
# These are coarse, maintained feature inputs rather than live API claims.
PARK_FACTOR_REFERENCE = {
    "american family field": 1.05,
    "angel stadium": 0.98,
    "busch stadium": 0.96,
    "camden yards": 1.02,
    "chase field": 1.03,
    "citi field": 0.97,
    "citizens bank park": 1.06,
    "comerica park": 0.98,
    "coors field": 1.16,
    "dodger stadium": 0.98,
    "fenway park": 1.04,
    "globe life field": 1.00,
    "great american ball park": 1.08,
    "guaranteed rate field": 1.01,
    "kauffman stadium": 0.99,
    "loanDepot park".lower(): 0.95,
    "minute maid park": 1.01,
    "nationals park": 1.00,
    "oracle park": 0.93,
    "petco park": 0.94,
    "pnc park": 0.97,
    "progressive field": 0.99,
    "rogers centre": 1.02,
    "safeco field": 0.95,
    "t-mobile park": 0.95,
    "target field": 0.99,
    "truist park": 1.02,
    "wrigley field": 1.01,
    "yankee stadium": 1.05,
}

# Venue coordinates are explicit reference data used only to fetch weather.
# They are not a betting-model fallback; unknown venues still leave weather blank.
VENUE_COORD_REFERENCE = {
    "american family field": (43.0280, -87.9712),
    "angel stadium": (33.8003, -117.8827),
    "busch stadium": (38.6226, -90.1928),
    "camden yards": (39.2840, -76.6217),
    "chase field": (33.4455, -112.0667),
    "citi field": (40.7571, -73.8458),
    "citizens bank park": (39.9061, -75.1665),
    "comerica park": (42.3390, -83.0485),
    "coors field": (39.7559, -104.9942),
    "dodger stadium": (34.0739, -118.2400),
    "fenway park": (42.3467, -71.0972),
    "globe life field": (32.7473, -97.0842),
    "great american ball park": (39.0979, -84.5082),
    "guaranteed rate field": (41.8300, -87.6339),
    "kauffman stadium": (39.0517, -94.4803),
    "loandepot park": (25.7781, -80.2197),
    "loan depot park": (25.7781, -80.2197),
    "minute maid park": (29.7573, -95.3555),
    "nationals park": (38.8730, -77.0074),
    "oracle park": (37.7786, -122.3893),
    "petco park": (32.7073, -117.1566),
    "pnc park": (40.4469, -80.0057),
    "progressive field": (41.4962, -81.6852),
    "rogers centre": (43.6414, -79.3894),
    "safeco field": (47.5914, -122.3325),
    "t-mobile park": (47.5914, -122.3325),
    "target field": (44.9817, -93.2777),
    "truist park": (33.8907, -84.4677),
    "wrigley field": (41.9484, -87.6553),
    "yankee stadium": (40.8296, -73.9262),
}

TEAM_ALIASES = {
    "arizona diamondbacks": ["ari", "arizona", "diamondbacks", "d-backs"],
    "atlanta braves": ["atl", "atlanta", "braves"],
    "baltimore orioles": ["bal", "baltimore", "orioles"],
    "boston red sox": ["bos", "boston", "red sox", "redsox"],
    "chicago cubs": ["chc", "cubs"],
    "chicago white sox": ["cws", "chw", "white sox", "whitesox"],
    "cincinnati reds": ["cin", "cincinnati", "reds"],
    "cleveland guardians": ["cle", "cleveland", "guardians"],
    "colorado rockies": ["col", "colorado", "rockies"],
    "detroit tigers": ["det", "detroit", "tigers"],
    "houston astros": ["hou", "houston", "astros"],
    "kansas city royals": ["kc", "kcr", "kansas city", "royals"],
    "los angeles angels": ["laa", "angels"],
    "los angeles dodgers": ["lad", "dodgers"],
    "miami marlins": ["mia", "miami", "marlins"],
    "milwaukee brewers": ["mil", "milwaukee", "brewers"],
    "minnesota twins": ["min", "minnesota", "twins"],
    "new york mets": ["nym", "mets"],
    "new york yankees": ["nyy", "yankees"],
    "athletics": ["ath", "oak", "oakland", "a's", "as"],
    "philadelphia phillies": ["phi", "philadelphia", "phillies"],
    "pittsburgh pirates": ["pit", "pittsburgh", "pirates"],
    "san diego padres": ["sd", "sdp", "san diego", "padres"],
    "san francisco giants": ["sf", "sfg", "san francisco", "giants"],
    "seattle mariners": ["sea", "seattle", "mariners"],
    "st. louis cardinals": ["stl", "st louis", "saint louis", "cardinals"],
    "tampa bay rays": ["tb", "tbr", "tampa bay", "rays"],
    "texas rangers": ["tex", "texas", "rangers"],
    "toronto blue jays": ["tor", "toronto", "blue jays", "bluejays"],
    "washington nationals": ["wsh", "was", "washington", "nationals"],
}

ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in TEAM_ALIASES.items():
    ALIAS_TO_CANONICAL[canonical] = canonical
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower()] = canonical


def load_dotenv(root: Path) -> None:
    for name in (".env", ".en"):
        path = root / name
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            pass


def fetch_json(url: str, *, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "mlb-app-phase17/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310 - controlled CLI URLs
        return json.loads(response.read().decode("utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        temp_name = tmp.name
    os.replace(temp_name, path)


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_atomic(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=str(path.parent), delete=False) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        temp_name = tmp.name
    os.replace(temp_name, path)


def norm_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_team(value: Any) -> str:
    n = norm_text(value)
    if not n:
        return ""
    if n in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[n]
    # Prefer full canonical match by contained city/nickname for messy labels.
    for canonical, aliases in TEAM_ALIASES.items():
        values = [canonical] + aliases
        for alias in values:
            alias_n = norm_text(alias)
            if alias_n and (n == alias_n or alias_n in n or n in alias_n):
                return canonical
    return n


def game_key(team_a: str, team_b: str) -> Tuple[str, str]:
    teams = sorted([canonical_team(team_a), canonical_team(team_b)])
    return (teams[0], teams[1]) if len(teams) == 2 else ("", "")


def row_date(row: Dict[str, str]) -> str:
    for key in ("date", "date_label", "game_date", "slate_date"):
        value = str(row.get(key, "")).strip()[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value
    return ""


def infer_row_teams(row: Dict[str, str]) -> Tuple[str, str]:
    team = row.get("team") or row.get("player_team") or row.get("team_abbr") or row.get("teamName") or ""
    opp = row.get("opponent") or row.get("opp") or row.get("opponent_team") or row.get("opponentName") or ""
    if team and opp:
        return canonical_team(team), canonical_team(opp)
    game = row.get("game") or row.get("matchup") or row.get("event") or row.get("event_name") or ""
    if "@" in game:
        away, home = game.split("@", 1)
        away_c, home_c = canonical_team(away), canonical_team(home)
        known = canonical_team(team) if team else ""
        if known == away_c:
            return away_c, home_c
        if known == home_c:
            return home_c, away_c
        return away_c, home_c
    if " vs " in game.lower():
        parts = re.split(r"\s+vs\.?\s+", game, flags=re.I)
        if len(parts) == 2:
            return canonical_team(parts[0]), canonical_team(parts[1])
    return canonical_team(team), canonical_team(opp)


def is_date_market_row(row: Dict[str, str], target_date: str, markets: Optional[set[str]]) -> bool:
    if row_date(row) != target_date:
        return False
    if not markets:
        return True
    market = (row.get("market") or row.get("prop_type") or row.get("market_key") or "").strip()
    return market in markets


def american_to_probability(value: Any) -> Optional[float]:
    try:
        odds = float(str(value).replace("+", "").strip())
    except Exception:
        return None
    if odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        f = float(str(value).replace("+", ""))
        if math.isnan(f):
            return None
        return f
    except Exception:
        return None


def round_str(value: Optional[float], digits: int = 3) -> str:
    if value is None:
        return ""
    return str(round(value, digits))


def c_to_f(value: Any) -> str:
    f = safe_float(value)
    return round_str((f * 9.0 / 5.0) + 32.0, 1) if f is not None else ""


def kph_to_mph(value: Any) -> str:
    f = safe_float(value)
    return round_str(f * 0.621371, 1) if f is not None else ""


@dataclass
class GameContext:
    game_pk: str
    game_date: str
    game_time_utc: str
    away_team: str
    home_team: str
    venue_name: str
    venue_city: str = ""
    venue_state: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def key(self) -> Tuple[str, str]:
        return game_key(self.away_team, self.home_team)


def fetch_mlb_schedule(date: str) -> Tuple[List[GameContext], Dict[str, Any], List[str]]:
    params = urllib.parse.urlencode({"sportId": 1, "date": date, "hydrate": "venue,team,probablePitcher"})
    payload = fetch_json(f"{MLB_SCHEDULE_URL}?{params}")
    warnings: List[str] = []
    games: List[GameContext] = []
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            teams = game.get("teams", {})
            away = teams.get("away", {}).get("team", {}).get("name", "")
            home = teams.get("home", {}).get("team", {}).get("name", "")
            venue = game.get("venue", {}) or {}
            venue_id = venue.get("id")
            venue_payload: Dict[str, Any] = {}
            location = venue.get("location") or {}
            coords = location.get("defaultCoordinates") or {}
            if venue_id and ("latitude" not in coords or "longitude" not in coords):
                try:
                    venue_payload = fetch_json(MLB_VENUE_URL.format(venue_id=venue_id))
                    venue_list = venue_payload.get("venues", [])
                    if venue_list:
                        venue_full = venue_list[0]
                        venue = {**venue, **venue_full}
                        location = venue_full.get("location") or location or {}
                        coords = location.get("defaultCoordinates") or coords or {}
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"venue coordinates unavailable for {venue.get('name') or venue_id}: {exc}")
            venue_name = str(venue.get("name") or "")
            latitude = safe_float(coords.get("latitude"))
            longitude = safe_float(coords.get("longitude"))
            if latitude is None or longitude is None:
                fallback_coords = VENUE_COORD_REFERENCE.get(norm_text(venue_name))
                if fallback_coords:
                    latitude, longitude = fallback_coords
            games.append(
                GameContext(
                    game_pk=str(game.get("gamePk", "")),
                    game_date=str(game.get("officialDate") or date),
                    game_time_utc=str(game.get("gameDate") or ""),
                    away_team=away,
                    home_team=home,
                    venue_name=venue_name,
                    venue_city=str(location.get("city") or ""),
                    venue_state=str(location.get("state") or location.get("stateAbbrev") or ""),
                    latitude=latitude,
                    longitude=longitude,
                )
            )
    return games, payload, warnings


def fetch_weather_for_games(date: str, games: Iterable[GameContext]) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}
    today = dt.date.today()
    target = dt.date.fromisoformat(date)
    for game in games:
        if game.latitude is None or game.longitude is None:
            warnings.append(f"weather skipped for {game.venue_name or game.game_pk}: missing coordinates")
            continue
        try:
            if target < today:
                params = {
                    "latitude": game.latitude,
                    "longitude": game.longitude,
                    "start_date": date,
                    "end_date": date,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                    "timezone": "America/New_York",
                }
                url = f"{OPEN_METEO_ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
            else:
                params = {
                    "latitude": game.latitude,
                    "longitude": game.longitude,
                    "start_date": date,
                    "end_date": date,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
                    "timezone": "America/New_York",
                }
                url = f"{OPEN_METEO_FORECAST_URL}?{urllib.parse.urlencode(params)}"
            payload = fetch_json(url)
            daily = payload.get("daily", {})
            temp_high_c = first_value(daily.get("temperature_2m_max"))
            temp_low_c = first_value(daily.get("temperature_2m_min"))
            wind_kph = first_value(daily.get("wind_speed_10m_max"))
            precip_probability = first_value(daily.get("precipitation_probability_max"))
            precip_sum = first_value(daily.get("precipitation_sum"))
            weather = {
                "weather_source": "open_meteo_archive" if target < today else "open_meteo_forecast",
                "weather_temperature_f": c_to_f(temp_high_c),
                "weather_temp_high_c": temp_high_c,
                "weather_temp_low_c": temp_low_c,
                "weather_precip_probability": precip_probability or precip_sum,
                "weather_precip_sum_mm": precip_sum,
                "weather_wind_mph": kph_to_mph(wind_kph),
                "weather_wind_speed_kph": wind_kph,
            }
            results[game.key] = weather
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"weather fetch failed for {game.venue_name or game.game_pk}: {exc}")
    return results, warnings


def first_value(values: Any) -> str:
    if isinstance(values, list) and values:
        return "" if values[0] is None else str(values[0])
    return "" if values is None else str(values)



def parse_game_line_events(events_payload: Any, *, date: str, source: str) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[str, Any], List[str]]:
    """Normalize a list/dict of game-line odds events into same-date game context.

    Supports the PropLine bulk odds shape and The Odds API shape: event -> bookmakers -> markets -> outcomes.
    """
    warnings: List[str] = []
    if isinstance(events_payload, dict):
        events = events_payload.get("events") or events_payload.get("data") or events_payload.get("results") or []
    else:
        events = events_payload if isinstance(events_payload, list) else []

    lines: Dict[Tuple[str, str], Dict[str, Any]] = {}
    target = dt.date.fromisoformat(date)
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        home = str(event.get("home_team") or event.get("homeTeam") or event.get("home") or "")
        away = str(event.get("away_team") or event.get("awayTeam") or event.get("away") or "")
        commence_raw = str(event.get("commence_time") or event.get("commenceTime") or event.get("date") or event.get("startTime") or "")
        if commence_raw:
            try:
                parsed = dt.datetime.fromisoformat(commence_raw.replace("Z", "+00:00"))
                event_date = parsed.astimezone(dt.timezone.utc).date() if parsed.tzinfo else parsed.date()
                if abs((event_date - target).days) > 1:
                    continue
            except Exception:
                pass
        home_c = canonical_team(home)
        away_c = canonical_team(away)
        if not home_c or not away_c:
            continue
        by_team_prices: Dict[str, List[float]] = {home_c: [], away_c: []}
        totals: List[float] = []
        books_seen: set[str] = set()
        for book in event.get("bookmakers", []) or event.get("books", []) or []:
            if not isinstance(book, dict):
                continue
            book_name = str(book.get("title") or book.get("key") or book.get("book") or book.get("sportsbook") or "")
            if book_name:
                books_seen.add(book_name)
            for market in book.get("markets", []) or []:
                if not isinstance(market, dict):
                    continue
                key = str(market.get("key") or market.get("market") or market.get("type") or "").lower()
                outcomes = market.get("outcomes", []) or []
                if key in {"h2h", "moneyline", "money_line"}:
                    for outcome in outcomes:
                        if not isinstance(outcome, dict):
                            continue
                        team = canonical_team(outcome.get("name") or outcome.get("description") or outcome.get("team"))
                        side = norm_text(outcome.get("side") or outcome.get("selection") or "")
                        if side == "home":
                            team = home_c
                        elif side == "away":
                            team = away_c
                        price = safe_float(outcome.get("price") or outcome.get("americanOdds") or outcome.get("odds"))
                        if team in by_team_prices and price is not None:
                            by_team_prices[team].append(price)
                elif key in {"totals", "total", "game_total"}:
                    for outcome in outcomes:
                        if not isinstance(outcome, dict):
                            continue
                        point = safe_float(outcome.get("point") or outcome.get("line") or outcome.get("total"))
                        if point is not None:
                            totals.append(point)
        home_ml = best_moneyline(by_team_prices.get(home_c, []))
        away_ml = best_moneyline(by_team_prices.get(away_c, []))
        game_total = sum(totals) / len(totals) if totals else None
        if home_ml is None and away_ml is None and game_total is None:
            continue
        lines[game_key(home, away)] = {
            "odds_source": source,
            "home_team_moneyline": round_str(home_ml, 0),
            "away_team_moneyline": round_str(away_ml, 0),
            "game_total": round_str(game_total, 2),
            "close_game_total": round_str(game_total, 2),
            "game_line_book_count": str(len(books_seen)) if books_seen else "",
        }
    if not lines:
        warnings.append(f"{source} returned no usable same-date MLB game lines")
    return lines, {"events": events if isinstance(events, list) else []}, warnings


def fetch_propline_game_lines(date: str) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[str, Any], List[str]]:
    try:
        from propline_value_client import get_bulk_game_lines, value_client_status
    except Exception as exc:  # noqa: BLE001
        return {}, {"events": []}, [f"PropLine game-line helper unavailable: {exc}"]
    try:
        payload = get_bulk_game_lines(markets=["h2h", "totals"], essential=False)
        lines, normalized_payload, warnings = parse_game_line_events(payload, date=date, source="propline_game_lines")
        try:
            normalized_payload["tokenGuard"] = value_client_status().get("tokenGuard", {})
        except Exception:
            pass
        return lines, normalized_payload, warnings
    except Exception as exc:  # noqa: BLE001
        return {}, {"events": []}, [f"PropLine game-line fetch failed: {exc}"]

def fetch_odds_api_lines(date: str, api_key: str) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[str, Any], List[str]]:
    warnings: List[str] = []
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "h2h,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    url = f"{ODDS_API_URL}?{urllib.parse.urlencode(params)}"
    try:
        payload = fetch_json(url)
    except Exception as exc:  # noqa: BLE001
        return {}, {"events": []}, [f"The Odds API game-line fetch failed: {exc}"]
    return parse_game_line_events(payload, date=date, source="the_odds_api")

def best_moneyline(prices: List[float]) -> Optional[float]:
    if not prices:
        return None
    # For a bettor, higher American odds are the better price, regardless of sign.
    return max(prices)


def implied_runs(total: Optional[float], team_ml: Optional[float], opp_ml: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    if total is None or team_ml is None or opp_ml is None or total <= 0:
        return None, None
    p_team = american_to_probability(team_ml)
    p_opp = american_to_probability(opp_ml)
    if p_team is None or p_opp is None or (p_team + p_opp) <= 0:
        return None, None
    share = p_team / (p_team + p_opp)
    team_runs = total * share
    return team_runs, total - team_runs


def enrich_playerboard(
    *,
    date: str,
    season: int,
    markets: Optional[set[str]],
    games: List[GameContext],
    weather_by_game: Dict[Tuple[str, str], Dict[str, Any]],
    odds_by_game: Dict[Tuple[str, str], Dict[str, Any]],
    dry_run: bool,
) -> Dict[str, Any]:
    path = PROJECT_ROOT / "data" / "playerboard" / f"playerboard_{season}.csv"
    rows = read_csv(path)
    if not rows:
        return {"status": "error", "message": f"Playerboard not found or empty: {path}", "path": str(path)}
    fields = list(rows[0].keys()) if rows else []
    new_fields = [
        "game_pk",
        "game_start_time_utc",
        "home_team",
        "away_team",
        "venue",
        "venue_name",
        "venue_city",
        "venue_state",
        "schedule_source",
        "game_context_source",
        "weather_source",
        "weather_temperature_f",
        "weather_temp_high_c",
        "weather_temp_low_c",
        "weather_precip_probability",
        "weather_precip_sum_mm",
        "weather_wind_mph",
        "weather_wind_speed_kph",
        "weather_wind_direction",
        "weather_humidity",
        "roof_status",
        "park_factor",
        "park_factor_source",
        "team_moneyline",
        "opponent_moneyline",
        "close_team_moneyline",
        "close_opponent_moneyline",
        "game_total",
        "close_game_total",
        "moneyline_implied_probability",
        "team_implied_runs",
        "opponent_implied_runs",
        "opponent_implied_runs_proxy",
        "implied_runs_source",
        "odds_source",
        "game_line_book_count",
    ]
    for field in new_fields:
        if field not in fields:
            fields.append(field)

    games_by_key = {g.key: g for g in games}
    updated = 0
    schedule_matches = 0
    weather_matches = 0
    odds_matches = 0
    park_matches = 0
    target_rows = 0
    missing = {"team_pair": 0, "schedule": 0, "weather": 0, "odds": 0, "park_factor": 0}

    for row in rows:
        if not is_date_market_row(row, date, markets):
            continue
        target_rows += 1
        team, opp = infer_row_teams(row)
        if not team or not opp:
            missing["team_pair"] += 1
            continue
        key = game_key(team, opp)
        game = games_by_key.get(key)
        if game:
            schedule_matches += 1
            row.update(
                {
                    "game_pk": game.game_pk,
                    "game_start_time_utc": game.game_time_utc,
                    "home_team": canonical_team(game.home_team),
                    "away_team": canonical_team(game.away_team),
                    "venue": game.venue_name,
                    "venue_name": game.venue_name,
                    "venue_city": game.venue_city,
                    "venue_state": game.venue_state,
                    "schedule_source": "mlb_stats_api",
                    "game_context_source": "mlb_stats_api",
                }
            )
            pf = PARK_FACTOR_REFERENCE.get(norm_text(game.venue_name))
            if pf is not None:
                park_matches += 1
                row["park_factor"] = round_str(pf, 3)
                row["park_factor_source"] = "local_venue_reference"
            else:
                missing["park_factor"] += 1
        else:
            missing["schedule"] += 1

        weather = weather_by_game.get(key)
        if weather:
            weather_matches += 1
            row.update({k: v for k, v in weather.items() if v is not None})
        else:
            missing["weather"] += 1

        odds = odds_by_game.get(key)
        if odds:
            odds_matches += 1
            is_home = team == canonical_team(game.home_team if game else row.get("home_team"))
            team_ml = safe_float(odds.get("home_team_moneyline" if is_home else "away_team_moneyline"))
            opp_ml = safe_float(odds.get("away_team_moneyline" if is_home else "home_team_moneyline"))
            total = safe_float(odds.get("game_total"))
            team_runs, opp_runs = implied_runs(total, team_ml, opp_ml)
            row.update(
                {
                    "team_moneyline": round_str(team_ml, 0),
                    "opponent_moneyline": round_str(opp_ml, 0),
                    "close_team_moneyline": round_str(team_ml, 0),
                    "close_opponent_moneyline": round_str(opp_ml, 0),
                    "game_total": odds.get("game_total", ""),
                    "close_game_total": odds.get("close_game_total", odds.get("game_total", "")),
                    "moneyline_implied_probability": round_str(american_to_probability(team_ml), 4),
                    "team_implied_runs": round_str(team_runs, 3),
                    "opponent_implied_runs": round_str(opp_runs, 3),
                    "opponent_implied_runs_proxy": round_str(opp_runs, 3),
                    "implied_runs_source": "moneyline_total_proxy" if team_runs is not None else "",
                    "odds_source": odds.get("odds_source", ""),
                    "game_line_book_count": odds.get("game_line_book_count", ""),
                }
            )
        else:
            missing["odds"] += 1
        updated += 1

    if not dry_run and updated:
        write_csv_atomic(path, fields, rows)

    return {
        "status": "ok",
        "dryRun": dry_run,
        "date": date,
        "season": season,
        "path": str(path),
        "targetRows": target_rows,
        "updatedRows": updated,
        "scheduleMatches": schedule_matches,
        "weatherMatches": weather_matches,
        "oddsMatches": odds_matches,
        "parkFactorMatches": park_matches,
        "missing": missing,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch same-date game context APIs and enrich Playerboard rows.")
    parser.add_argument("--date", required=True, help="Slate date YYYY-MM-DD")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--markets", nargs="*", default=[])
    parser.add_argument("--skip-weather", action="store_true")
    parser.add_argument("--skip-odds", action="store_true", help="Legacy alias for --line-source none")
    parser.add_argument("--line-source", choices=["propline", "the_odds_api", "none"], default="propline", help="Game-line source. Default uses PropLine; The Odds API is optional fallback.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT)
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    warnings: List[str] = []
    games, schedule_payload, schedule_warnings = fetch_mlb_schedule(args.date)
    warnings.extend(schedule_warnings)
    write_json(WAREHOUSE_DIR / f"mlb_schedule_{args.date}.json", schedule_payload)

    weather_by_game: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if args.skip_weather:
        warnings.append("weather fetch skipped by flag")
    else:
        weather_by_game, weather_warnings = fetch_weather_for_games(args.date, games)
        warnings.extend(weather_warnings)
        write_json(WAREHOUSE_DIR / f"weather_{args.date}.json", {"date": args.date, "games": {"|".join(k): v for k, v in weather_by_game.items()}})

    odds_by_game: Dict[Tuple[str, str], Dict[str, Any]] = {}
    odds_payload: Dict[str, Any] = {"events": []}
    selected_line_source = "none" if args.skip_odds else args.line_source
    if selected_line_source == "none":
        warnings.append("game-line odds fetch skipped by flag/source")
    elif selected_line_source == "propline":
        odds_by_game, odds_payload, odds_warnings = fetch_propline_game_lines(args.date)
        warnings.extend(odds_warnings)
        write_json(WAREHOUSE_DIR / f"game_lines_{args.date}.json", {"date": args.date, "source": "propline", "events": odds_payload.get("events", []), "tokenGuard": odds_payload.get("tokenGuard", {})})
    elif selected_line_source == "the_odds_api":
        api_key = os.environ.get("THE_ODDS_API_KEY") or os.environ.get("ODDS_API_KEY")
        if not api_key:
            warnings.append("THE_ODDS_API_KEY/ODDS_API_KEY not set; game-line odds fields left blank")
        else:
            odds_by_game, odds_payload, odds_warnings = fetch_odds_api_lines(args.date, api_key)
            warnings.extend(odds_warnings)
            safe_payload = {"date": args.date, "source": "the_odds_api", "events": odds_payload.get("events", [])}
            write_json(WAREHOUSE_DIR / f"game_lines_{args.date}.json", safe_payload)

    # Maintain the explicit park-factor reference so users can inspect/replace it.
    park_path = REFERENCE_DIR / "park_factors.csv"
    if not park_path.exists():
        write_csv_atomic(
            park_path,
            ["venue_name", "park_factor", "source"],
            [
                {"venue_name": venue, "park_factor": value, "source": "local_venue_reference"}
                for venue, value in sorted(PARK_FACTOR_REFERENCE.items())
            ],
        )

    markets = set(args.markets) if args.markets else None
    enrichment = enrich_playerboard(
        date=args.date,
        season=args.season,
        markets=markets,
        games=games,
        weather_by_game=weather_by_game,
        odds_by_game=odds_by_game,
        dry_run=args.dry_run,
    )

    payload = {
        "status": "ok" if enrichment.get("status") == "ok" else "warning",
        "date": args.date,
        "season": args.season,
        "markets": args.markets,
        "scheduleGames": len(games),
        "weatherGames": len(weather_by_game),
        "oddsGames": len(odds_by_game),
        "lineSource": selected_line_source,
        "enrichment": enrichment,
        "warnings": warnings,
        "outputs": {
            "schedule": str(WAREHOUSE_DIR / f"mlb_schedule_{args.date}.json"),
            "weather": str(WAREHOUSE_DIR / f"weather_{args.date}.json"),
            "gameLines": str(WAREHOUSE_DIR / f"game_lines_{args.date}.json"),
            "parkFactors": str(park_path),
        },
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
