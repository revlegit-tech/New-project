"""Shared helpers for Phase 16 live feature parity.

Phase 16 focuses on making live Playerboard rows carry the same *eligible live*
features that model tooling expects, while explicitly blocking leakage columns
such as final outcomes from being treated as runtime predictors.
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
ODDS_DIR = DATA_DIR / "odds"
MODELS_DIR = DATA_DIR / "models"
AUDIT_DIR = MODELS_DIR / "audits"

DEFAULT_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]

# These columns may exist in training data, but they are not safe/valid live
# prediction inputs. A market containing them in model metadata must remain
# experimental until it is retrained without leakage.
LEAKAGE_FEATURES = {
    "actual",
    "result",
    "target",
    "label",
    "hit",
    "won",
    "outcome",
    "settled",
    "graded",
    "final_score",
    "finalScore",
}

IDENTIFIER_ONLY_FEATURES = {
    "event_id",
    "eventId",
    "game_id",
    "gameId",
    "player_id",
    "playerId",
}

LIVE_FEATURES = [
    "line",
    "american_odds",
    "sportsbook_count",
    "best_book",
    "best_american_odds",
    "sportsbook_implied_probability",
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
    "opponent_rate",
    "park_factor",
]

FIELD_ALIASES = {
    "player": ["player", "player_name", "name"],
    "market": ["market", "baseMarket", "originalMarket"],
    "line": ["line", "propLine", "value"],
    "team": ["team", "teamAbbr", "homeTeam", "awayTeam"],
    "opponent": ["opponent", "opp", "opponentAbbr"],
    "american_odds": ["american_odds", "americanOdds", "odds", "price", "bestAmericanOdds"],
    "book": ["book", "sportsbook", "bookmaker", "bookmakerTitle", "bestBook"],
    "event_id": ["event_id", "eventId", "game_id", "gameId"],
}


def project_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str] | None = None) -> None:
    rows = [dict(row) for row in rows]
    ordered: list[str] = []
    if fieldnames:
        ordered.extend(str(name) for name in fieldnames if str(name) not in ordered)
    for row in rows:
        for key in row.keys():
            if key not in ordered:
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


def first_value(row: dict[str, Any], names: Iterable[str], default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def normalized_market(row_or_value: dict[str, Any] | Any) -> str:
    if isinstance(row_or_value, dict):
        value = first_value(row_or_value, FIELD_ALIASES["market"])
    else:
        value = row_or_value
    value = normalized_text(value)
    value = value.replace(" ", "_").replace("-", "_")
    return value


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace("%", "")
    if raw == "":
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


def normalized_line(value: Any) -> str:
    parsed = parse_float(value)
    if parsed is None:
        return normalized_text(value)
    return f"{parsed:.3f}".rstrip("0").rstrip(".")


def match_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    player = normalized_text(first_value(row, FIELD_ALIASES["player"]))
    market = normalized_market(row)
    line = normalized_line(first_value(row, FIELD_ALIASES["line"]))
    # raw label/direction helps keep Over/Under alt markets distinct when present.
    direction = normalized_text(first_value(row, ["rawLabel", "side", "label", "outcome"], "over"))
    if direction in {"yes", "1+", "2+", "3+"} or direction.endswith(")"):
        direction = "over"
    return (player, market, line, direction)


def implied_probability_from_american(odds: Any) -> float | None:
    value = parse_float(odds)
    if value is None or value == 0:
        return None
    if value > 0:
        return 100.0 / (value + 100.0)
    return abs(value) / (abs(value) + 100.0)


def best_book_price(rows: list[dict[str, Any]]) -> tuple[int | None, str, list[dict[str, Any]]]:
    books: list[dict[str, Any]] = []
    best_odds: int | None = None
    best_book = ""
    for row in rows:
        odds = parse_int(first_value(row, FIELD_ALIASES["american_odds"]))
        if odds is None:
            continue
        book = first_value(row, FIELD_ALIASES["book"], "Unknown")
        event_id = first_value(row, FIELD_ALIASES["event_id"])
        books.append({"book": book, "americanOdds": odds, "eventId": event_id})
        # Higher American odds are always the better payout for the same side.
        if best_odds is None or odds > best_odds:
            best_odds = odds
            best_book = book
    books.sort(key=lambda item: item.get("americanOdds", -9999), reverse=True)
    return best_odds, best_book, books


def playerboard_path(season: int) -> Path:
    return PLAYERBOARD_DIR / f"playerboard_{season}.csv"


def propline_path(date: str) -> Path:
    return ODDS_DIR / f"propline_props_{date}.csv"


def metadata_path(market: str) -> Path:
    return MODELS_DIR / f"prop_model_{market}_features.json"


def metadata_features(market: str) -> list[str]:
    payload = read_json(metadata_path(market), default={})
    if isinstance(payload, list):
        return [str(item) for item in payload]
    if isinstance(payload, dict):
        for key in ("features", "feature_names", "columns", "featureColumns"):
            value = payload.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
    return []


def eligible_live_features(features: Iterable[str]) -> list[str]:
    out: list[str] = []
    blocked = LEAKAGE_FEATURES | IDENTIFIER_ONLY_FEATURES
    for feature in features:
        name = str(feature)
        if name in blocked:
            continue
        if name not in out:
            out.append(name)
    return out


def row_date(row: dict[str, Any]) -> str:
    return first_value(row, ["date", "gameDate", "eventDate", "slateDate", "createdDate"])


def filter_rows(rows: list[dict[str, Any]], market: str | None = None, date: str | None = None) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        if market and normalized_market(row) != normalized_market(market):
            continue
        if date and row_date(row) and row_date(row) != date:
            continue
        selected.append(row)
    return selected


def feature_coverage(rows: list[dict[str, Any]], features: list[str]) -> dict[str, Any]:
    details = []
    for feature in features:
        present = 0
        numeric = 0
        for row in rows:
            value = row.get(feature)
            if value is not None and str(value).strip() != "":
                present += 1
                if parse_float(value) is not None:
                    numeric += 1
        count = max(1, len(rows))
        details.append(
            {
                "feature": feature,
                "presentRows": present,
                "numericRows": numeric,
                "coverage": round(present / count, 4),
                "numericCoverage": round(numeric / count, 4),
            }
        )
    return {
        "rowCount": len(rows),
        "featureCount": len(features),
        "averageNumericCoverage": round(sum(item["numericCoverage"] for item in details) / max(1, len(details)), 4),
        "features": details,
    }
