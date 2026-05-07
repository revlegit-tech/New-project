from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATS_DIR = ROOT / "data" / "cache" / "incremental_stats"

_CSV_CACHE: dict[tuple[str, int, int], list[dict[str, str]]] = {}

BATTER_MARKET_STATS = {
    "batter_hits": "hits",
    "batter_total_bases": "totalBases",
    "batter_home_runs": "homeRuns",
    "batter_rbis": "rbi",
    "batter_rbi": "rbi",
    "batter_runs": "runs",
    "batter_stolen_bases": "stolenBases",
    "batter_singles": "hits",
}

PITCHER_MARKET_STATS = {
    "pitcher_strikeouts": "strikeOuts",
    "pitcher_hits_allowed": "hits",
    "pitcher_earned_runs": "earnedRuns",
    "pitcher_walks": "baseOnBalls",
    "pitcher_home_runs_allowed": "homeRuns",
}

TEAM_MARKET_STATS = {
    "team_total_runs": "runs",
}

WINDOW_KEYS = ("L5", "L10", "L20", "H2H", "season", "prevSeason")

# StatsAPI, legacy Lahman-style feeds, and playerboard exports do not always
# agree on team abbreviations. Normalize at the source so hit-rate joins keep
# their six-part key intact across playerboard and game-log caches.
TEAM_NORM = {
    "SFG": "SF", "CWS": "CHW", "KCR": "KC", "TBR": "TB",
    "SDP": "SD", "WSN": "WSH", "SLN": "STL", "CHN": "CHC",
    "ANA": "LAA", "MON": "WSH",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any, default: float | None = 0.0) -> float | None:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def to_int(value: Any, default: int) -> int:
    parsed = to_float(value, None)
    if parsed is None:
        return default
    return int(parsed)


def normalize_market(value: Any) -> str:
    text = clean(value).lower().replace("-", "_").replace(" ", "_")
    return re.sub(r"_+", "_", text)


def base_market(value: Any) -> str:
    market = normalize_market(value)
    return market[:-4] if market.endswith("_alt") else market


def normalize_name(value: Any) -> str:
    text = clean(value).casefold()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text).strip()


def normalize_team(value: Any) -> str:
    team = clean(value).upper()
    return TEAM_NORM.get(team, team)


def parse_date(value: Any) -> date | None:
    text = clean(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def row_date(row: dict[str, Any]) -> date | None:
    return parse_date(row.get("date"))


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _CSV_CACHE.get(key)
    if cached is not None:
        return cached
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _CSV_CACHE[key] = rows
    return rows


def source_for_market(market: Any) -> tuple[str, str] | None:
    base = base_market(market)
    if base in BATTER_MARKET_STATS:
        return ("batter_game_logs", BATTER_MARKET_STATS[base])
    if base in PITCHER_MARKET_STATS:
        return ("pitcher_game_logs", PITCHER_MARKET_STATS[base])
    if base in TEAM_MARKET_STATS:
        return ("team_game_logs", TEAM_MARKET_STATS[base])
    return None


def logs_for_source(season: int, source: str) -> list[dict[str, str]]:
    return csv_rows(STATS_DIR / f"{source}_{season}.csv")


def direction_for_row(row: dict[str, Any]) -> str:
    text = f"{clean(row.get('rawLabel'))} {clean(row.get('marketDisplay'))}".lower()
    if "under" in text:
        return "under"
    if "over" in text:
        return "over"
    if re.search(r"\d+\s*\+", text):
        return "over"
    return "under"


def subject_rows(
    rows: list[dict[str, str]],
    source: str,
    row: dict[str, Any],
    target_date: date | None,
) -> list[dict[str, str]]:
    player_name = normalize_name(row.get("player"))
    team = normalize_team(row.get("team") or row.get("player"))
    matched: list[dict[str, str]] = []

    for item in rows:
        if source == "team_game_logs":
            if normalize_team(item.get("team")) != team:
                continue
        elif normalize_name(item.get("player")) != player_name:
            continue

        played_on = row_date(item)
        if target_date and played_on and played_on >= target_date:
            continue
        matched.append(item)

    return sorted(matched, key=lambda item: (clean(item.get("date")), clean(item.get("gamePk"))))


def null_windows() -> dict[str, None]:
    return {key: None for key in WINDOW_KEYS}


def hit_summary(
    rows: list[dict[str, str]],
    stat_key: str,
    line: float,
    direction: str,
) -> dict[str, int] | None:
    if not rows:
        return None

    total = 0
    hits = 0
    for row in rows:
        value = to_float(row.get(stat_key), None)
        if value is None:
            continue
        total += 1
        if direction == "under":
            hits += int(value < line)
        else:
            hits += int(value >= line)

    if total == 0:
        return None
    return {"hits": hits, "total": total, "pct": round(hits * 100 / total)}


def canonical_line(row: dict[str, Any]) -> str:
    text = clean(row.get("line"))
    parsed = to_float(text, None)
    if parsed is None:
        return text
    return f"{parsed:g}"


def canonical_side(row: dict[str, Any]) -> str:
    raw = clean(row.get("rawLabel"))
    if raw:
        return raw.casefold()
    return "under" if direction_for_row(row) == "under" else "over"


def row_key(row: dict[str, Any]) -> str:
    parts = [
        normalize_name(row.get("player")),
        normalize_market(row.get("market")),
        normalize_team(row.get("team")),
        normalize_team(row.get("opponent")),
        canonical_line(row),
        canonical_side(row),
    ]
    return "|".join(parts)


def response_for_row(row: dict[str, Any], season: int, target_date: date | None) -> dict[str, Any]:
    market = normalize_market(row.get("market"))
    source = source_for_market(market)
    line = to_float(row.get("line"), 0.5)
    if line is None:
        line = 0.5

    payload: dict[str, Any] = {
        "key": row_key(row),
        "player": clean(row.get("player")),
        "team": normalize_team(row.get("team")),
        "opponent": normalize_team(row.get("opponent")),
        "market": market,
        "line": line,
        "rawLabel": clean(row.get("rawLabel")) or ("Under" if direction_for_row(row) == "under" else "Over"),
        **null_windows(),
    }

    if source is None:
        return payload

    source_name, stat_key = source
    direction = direction_for_row(row)
    current_logs = subject_rows(logs_for_source(season, source_name), source_name, row, target_date)
    prior_logs = subject_rows(logs_for_source(season - 1, source_name), source_name, row, None)

    h2h_logs = [
        item for item in current_logs
        if normalize_team(item.get("opponent")) == normalize_team(row.get("opponent"))
    ]

    payload.update({
        "L5": hit_summary(current_logs[-5:], stat_key, line, direction),
        "L10": hit_summary(current_logs[-10:], stat_key, line, direction),
        "L20": hit_summary(current_logs[-20:], stat_key, line, direction),
        "H2H": hit_summary(h2h_logs, stat_key, line, direction),
        "season": hit_summary(current_logs, stat_key, line, direction),
        "prevSeason": hit_summary(prior_logs, stat_key, line, direction),
    })
    return payload


def single_query_row(query: dict[str, list[str]]) -> dict[str, Any] | None:
    player = clean(first(query, "player"))
    team = clean(first(query, "team"))
    market = clean(first(query, "market"))
    if not player or not market:
        return None
    return {
        "player": player,
        "team": team,
        "opponent": clean(first(query, "opponent")),
        "market": market,
        "marketDisplay": clean(first(query, "marketDisplay")),
        "line": clean(first(query, "line")) or "0.5",
        "rawLabel": clean(first(query, "rawLabel")),
    }


def first(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    return values[0] if values else default


def playerboard_rows(query: dict[str, list[str]], season: int, limit: int) -> tuple[str, list[dict[str, Any]]]:
    direct = single_query_row(query)
    if direct:
        return ("single_query", [direct])

    from playerboard import load_saved_playerboard

    payload = load_saved_playerboard(
        season=season,
        date_label=clean(first(query, "date")),
        market=clean(first(query, "market")),
        limit=limit,
    )
    rows = payload.get("top") if isinstance(payload, dict) else []
    return (clean(payload.get("source")) or "saved_playerboard", rows if isinstance(rows, list) else [])


def player_hit_rates_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = to_int(first(query, "season", "2026"), 2026)
    limit = max(1, min(to_int(first(query, "limit", "500"), 500), 5000))
    target_date = parse_date(first(query, "date"))

    source, rows = playerboard_rows(query, season, limit)
    responses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = response_for_row(row, season, target_date)
        key = clean(item.get("key"))
        if key in seen:
            continue
        seen.add(key)
        responses.append(item)

    return {
        "ok": True,
        "season": season,
        "date": clean(first(query, "date")),
        "market": clean(first(query, "market")),
        "source": source,
        "rowsLoaded": len(responses),
        "rows": responses,
    }
