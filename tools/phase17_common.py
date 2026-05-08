"""Shared helpers for Phase 17 game-context enrichment.

Phase 17 adds same-date game context to live Playerboard rows without
fabricating unavailable data. Values are populated only when a local schedule,
game-line, weather, park-factor, or daily-summary file explicitly contains the
source fields needed to derive them.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PLAYERBOARD_DIR = DATA_DIR / "playerboard"
MODELS_DIR = DATA_DIR / "models"
AUDIT_DIR = MODELS_DIR / "audits"
WAREHOUSE_DIR = DATA_DIR / "warehouse"

DEFAULT_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]

TEAM_ALIASES = {
    "ari": "arizona diamondbacks",
    "atl": "atlanta braves",
    "bal": "baltimore orioles",
    "bos": "boston red sox",
    "chc": "chicago cubs",
    "chw": "chicago white sox",
    "cws": "chicago white sox",
    "cin": "cincinnati reds",
    "cle": "cleveland guardians",
    "col": "colorado rockies",
    "det": "detroit tigers",
    "hou": "houston astros",
    "kc": "kansas city royals",
    "kcr": "kansas city royals",
    "laa": "los angeles angels",
    "lad": "los angeles dodgers",
    "mia": "miami marlins",
    "mil": "milwaukee brewers",
    "min": "minnesota twins",
    "nym": "new york mets",
    "nyy": "new york yankees",
    "oak": "oakland athletics",
    "ath": "athletics",
    "phi": "philadelphia phillies",
    "pit": "pittsburgh pirates",
    "sd": "san diego padres",
    "sdp": "san diego padres",
    "sea": "seattle mariners",
    "sf": "san francisco giants",
    "sfg": "san francisco giants",
    "stl": "st louis cardinals",
    "tb": "tampa bay rays",
    "tbr": "tampa bay rays",
    "tex": "texas rangers",
    "tor": "toronto blue jays",
    "wsh": "washington nationals",
    "was": "washington nationals",
}

FIELD_ALIASES: dict[str, list[str]] = {
    "date": ["date", "gameDate", "eventDate", "slateDate", "startDate", "commenceDate"],
    "market": ["market", "baseMarket", "originalMarket"],
    "team": ["team", "teamAbbr", "team_abbr", "playerTeam", "player_team"],
    "opponent": ["opponent", "opp", "opponentAbbr", "opponent_abbr"],
    "home_team": ["home_team", "homeTeam", "home", "home_name", "homeName"],
    "away_team": ["away_team", "awayTeam", "away", "away_name", "awayName"],
    "event_id": ["event_id", "eventId", "game_id", "gameId", "id", "event"],
    "game": ["game", "matchup", "name", "eventName", "game_name"],
    "venue": ["venue", "park", "ballpark", "stadium", "venue_name"],
    "home_moneyline": ["home_moneyline", "homeMoneyline", "home_ml", "homeML", "home_price", "homeOdds", "home_american_odds"],
    "away_moneyline": ["away_moneyline", "awayMoneyline", "away_ml", "awayML", "away_price", "awayOdds", "away_american_odds"],
    "open_home_moneyline": ["open_home_moneyline", "home_open_moneyline", "openHomeMoneyline", "open_home_ml"],
    "open_away_moneyline": ["open_away_moneyline", "away_open_moneyline", "openAwayMoneyline", "open_away_ml"],
    "close_home_moneyline": ["close_home_moneyline", "home_close_moneyline", "closeHomeMoneyline", "close_home_ml"],
    "close_away_moneyline": ["close_away_moneyline", "away_close_moneyline", "closeAwayMoneyline", "close_away_ml"],
    "game_total": ["game_total", "gameTotal", "total", "over_under", "overUnder", "total_line", "ou", "run_total"],
    "open_game_total": ["open_game_total", "openGameTotal", "open_total", "opening_total", "openOU"],
    "close_game_total": ["close_game_total", "closeGameTotal", "close_total", "closing_total", "closeOU"],
    "temperature": ["temperature", "temp", "temp_f", "temperature_f", "weather_temp", "weatherTemperature"],
    "wind_speed": ["wind_speed", "windSpeed", "wind_mph", "wind", "weather_wind_speed"],
    "wind_direction": ["wind_direction", "windDirection", "wind_dir", "weather_wind_direction"],
    "humidity": ["humidity", "weather_humidity"],
    "precip_probability": ["precip_probability", "precipProbability", "precip", "rain_probability"],
    "roof": ["roof", "roof_status", "roofStatus"],
    "park_factor": ["park_factor", "parkFactor", "run_factor", "runFactor", "pf"],
}

CONTEXT_FIELDS = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
    "park_factor",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_wind_direction",
    "weather_humidity",
    "weather_precip_probability",
    "roof_status",
    "venue",
    "game_context_source",
]

STRING_CONTEXT_FIELDS = {
    "weather_wind_direction",
    "roof_status",
    "venue",
    "game_context_source",
}

SKIP_CONTEXT_SCAN_PARTS = {
    "playerboard",
    "training",
    "models",
    "cache",
    "__pycache__",
}


def normalized_text(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace("&", "and")
    raw = raw.replace(".", "")
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return TEAM_ALIASES.get(raw, raw)


def canonical_team(value: Any) -> str:
    text = normalized_text(value)
    return TEAM_ALIASES.get(text, text)


def normalized_market(row_or_value: dict[str, Any] | Any) -> str:
    if isinstance(row_or_value, dict):
        value = first_value(row_or_value, FIELD_ALIASES["market"])
    else:
        value = row_or_value
    return normalized_text(value).replace(" ", "_").replace("-", "_")


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace("%", "")
    if raw == "" or raw.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(round(parsed))


def first_value(row: dict[str, Any], names: Iterable[str], default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str] | None = None) -> None:
    rows = [dict(row) for row in rows]
    ordered: list[str] = []
    if fieldnames:
        ordered.extend(str(name) for name in fieldnames if str(name) not in ordered)
    for row in rows:
        for key in row.keys():
            if str(key) not in ordered:
                ordered.append(str(key))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ordered, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def playerboard_path(season: int) -> Path:
    return PLAYERBOARD_DIR / f"playerboard_{season}.csv"


def row_date(row: dict[str, Any]) -> str:
    return first_value(row, FIELD_ALIASES["date"])


def filter_rows(rows: list[dict[str, Any]], market: str | None = None, date: str | None = None) -> list[dict[str, Any]]:
    selected = []
    wanted_market = normalized_market(market) if market else ""
    for row in rows:
        if wanted_market and normalized_market(row) != wanted_market:
            continue
        if date and row_date(row) and row_date(row) != date:
            continue
        selected.append(row)
    return selected


def implied_probability_from_american(odds: Any) -> float | None:
    value = parse_float(odds)
    if value is None or value == 0:
        return None
    if value > 0:
        return 100.0 / (value + 100.0)
    return abs(value) / (abs(value) + 100.0)


def implied_runs_from_total_and_moneylines(team_ml: Any, opponent_ml: Any, total: Any) -> tuple[float | None, float | None, str]:
    """Derive a conservative implied-run proxy from total + moneyline.

    This is intentionally labelled as a proxy. It is not written unless both
    sides' moneyline and the game total exist in local source files.
    """
    total_value = parse_float(total)
    team_prob = implied_probability_from_american(team_ml)
    opp_prob = implied_probability_from_american(opponent_ml)
    if total_value is None or team_prob is None or opp_prob is None or (team_prob + opp_prob) <= 0:
        return None, None, ""
    share = team_prob / (team_prob + opp_prob)
    # Keep the split close to the game total while avoiding extreme allocations.
    share = max(0.25, min(0.75, share))
    team_runs = round(total_value * share, 3)
    opp_runs = round(total_value - team_runs, 3)
    return team_runs, opp_runs, "moneyline_total_proxy"


def moneyline_move(open_ml: Any, close_ml: Any) -> float | None:
    open_value = parse_float(open_ml)
    close_value = parse_float(close_ml)
    if open_value is None or close_value is None:
        return None
    return round(close_value - open_value, 3)


def total_move(open_total: Any, close_total: Any) -> float | None:
    open_value = parse_float(open_total)
    close_value = parse_float(close_total)
    if open_value is None or close_value is None:
        return None
    return round(close_value - open_value, 3)


def feature_coverage(rows: list[dict[str, Any]], features: list[str], string_fields: set[str] | None = None) -> dict[str, Any]:
    string_fields = string_fields or set()
    details = []
    for feature in features:
        present = 0
        numeric = 0
        for row in rows:
            value = row.get(feature)
            if value is not None and str(value).strip() != "":
                present += 1
                if feature in string_fields or parse_float(value) is not None:
                    numeric += 1
        count = max(1, len(rows))
        details.append(
            {
                "feature": feature,
                "presentRows": present,
                "numericRows": numeric,
                "coverage": round(present / count, 4),
                "numericCoverage": round(numeric / count, 4),
                "fieldType": "string" if feature in string_fields else "numeric",
            }
        )
    return {
        "rowCount": len(rows),
        "featureCount": len(features),
        "averageNumericCoverage": round(sum(item["numericCoverage"] for item in details) / max(1, len(details)), 4),
        "features": details,
    }


def flatten_json_records(payload: Any) -> list[dict[str, Any]]:
    """Extract likely game/context records from nested JSON payloads."""
    records: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        keys = {str(key) for key in value.keys()}
        has_team = any(key in keys for key in FIELD_ALIASES["home_team"] + FIELD_ALIASES["away_team"])
        has_game = any(key in keys for key in FIELD_ALIASES["game"] + FIELD_ALIASES["event_id"])
        has_context = any(
            key in keys
            for key in (
                FIELD_ALIASES["home_moneyline"]
                + FIELD_ALIASES["away_moneyline"]
                + FIELD_ALIASES["game_total"]
                + FIELD_ALIASES["temperature"]
                + FIELD_ALIASES["park_factor"]
            )
        )
        if has_context or (has_team and has_game):
            records.append(dict(value))
        for key in ("games", "events", "schedule", "summaries", "gameSummaries", "weather", "odds", "lines"):
            if key in value:
                walk(value[key])

    walk(payload)
    return records


def should_scan_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if parts.intersection(SKIP_CONTEXT_SCAN_PARTS):
        return False
    name = path.name.lower()
    if "propline_props" in name or "playerboard" in name or "training" in name:
        return False
    return True


def source_candidates(date: str) -> list[Path]:
    candidates: list[Path] = []
    explicit = [
        WAREHOUSE_DIR / "summaries" / f"daily_summary_{date}.json",
        WAREHOUSE_DIR / "summaries" / f"game_summary_{date}.json",
        WAREHOUSE_DIR / "game_summaries" / f"{date}.json",
        WAREHOUSE_DIR / "schedule" / f"mlb_schedule_{date}.csv",
        WAREHOUSE_DIR / "schedules" / f"mlb_schedule_{date}.csv",
        WAREHOUSE_DIR / "weather" / f"weather_{date}.csv",
        WAREHOUSE_DIR / "weather" / f"weather_{date}.json",
        WAREHOUSE_DIR / "odds_snapshots" / f"game_lines_{date}.csv",
        WAREHOUSE_DIR / "odds_snapshots" / f"mlb_game_odds_{date}.csv",
        WAREHOUSE_DIR / "odds_snapshots" / f"odds_movement_{date}.csv",
        DATA_DIR / "schedule" / f"mlb_schedule_{date}.csv",
        DATA_DIR / "weather" / f"weather_{date}.csv",
        DATA_DIR / "odds" / f"game_lines_{date}.csv",
        DATA_DIR / "odds" / f"odds_movement_{date}.csv",
    ]
    for path in explicit:
        if path.exists() and path not in candidates:
            candidates.append(path)
    if DATA_DIR.exists():
        for path in DATA_DIR.rglob(f"*{date}*"):
            if path.suffix.lower() not in {".csv", ".json"}:
                continue
            if path not in candidates and should_scan_path(path):
                candidates.append(path)
    return candidates
