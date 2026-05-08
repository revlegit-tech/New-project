#!/usr/bin/env python3
"""Build canonical game-context markets and join them back onto Playerboard.

Phase 17 v4 separates game/team context from batter/pitcher prop markets.
The canonical source-of-truth output is:
  data/warehouse/game_context/game_context_<date>.csv
  data/warehouse/game_context/game_context_markets_<date>.csv

Playerboard rows still receive a denormalized copy for hot-path UI reads, but
moneyline/total/implied-run values are treated as Game Context, not batter data.

No silent fallbacks:
- game_total is only set when a provider payload or existing source row contains it
- implied runs are only computed when real game total + moneylines exist
- missing fields are recorded explicitly
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
PLAYERBOARD_DIR = ROOT / "data" / "playerboard"
GAME_CONTEXT_DIR = ROOT / "data" / "warehouse" / "game_context"
AUDIT_DIR = ROOT / "data" / "warehouse" / "audits"

try:  # Prefer the v3 parser when present.
    from tools.phase17_apply_propline_game_lines import (  # type: ignore
        GameLine,
        implied_runs_proxy,
        moneyline_to_probability,
        norm_team,
        parse_game_lines,
        row_date,
        row_market,
        row_team_pair,
        to_float,
    )
except Exception:  # pragma: no cover - fallback for isolated tests.
    @dataclass
    class GameLine:  # type: ignore[no-redef]
        away: str
        home: str
        event_id: str = ""
        source: str = "provider"
        book: str = ""
        moneylines: Dict[str, float] = field(default_factory=dict)
        total: Optional[float] = None

        @property
        def key(self) -> Tuple[str, str]:
            return tuple(sorted([self.away, self.home]))

    _ALIASES = {
        "bos": "boston red sox", "boston": "boston red sox", "red sox": "boston red sox",
        "nyy": "new york yankees", "yankees": "new york yankees",
    }

    def norm_team(value: Any) -> str:  # type: ignore[no-redef]
        text = str(value or "").strip().lower()
        text = text.replace(".", "")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return _ALIASES.get(text, text)

    def to_float(value: Any) -> Optional[float]:  # type: ignore[no-redef]
        try:
            if value is None or value == "":
                return None
            out = float(str(value).replace("%", "").strip())
            return out if math.isfinite(out) else None
        except Exception:
            return None

    def moneyline_to_probability(odds: Optional[float]) -> Optional[float]:  # type: ignore[no-redef]
        if odds is None or odds == 0:
            return None
        return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)

    def implied_runs_proxy(total: Optional[float], team_ml: Optional[float], opp_ml: Optional[float]) -> Tuple[Optional[float], Optional[float]]:  # type: ignore[no-redef]
        if total is None or team_ml is None or opp_ml is None:
            return None, None
        tp, op = moneyline_to_probability(team_ml), moneyline_to_probability(opp_ml)
        if tp is None or op is None or tp + op <= 0:
            return None, None
        share = tp / (tp + op)
        adj = max(-0.5, min(0.5, share - 0.5)) * 2.25
        team_runs = max(0.0, min(total, total / 2.0 + adj))
        return round(team_runs, 3), round(total - team_runs, 3)

    def row_date(row: Dict[str, str]) -> str:  # type: ignore[no-redef]
        for key in ("date", "game_date", "slate_date", "eventDateLocal"):
            if row.get(key):
                return str(row[key])[:10]
        return ""

    def row_market(row: Dict[str, str]) -> str:  # type: ignore[no-redef]
        return str(row.get("market") or row.get("market_key") or row.get("prop_market") or row.get("stat") or "")

    def row_team_pair(row: Dict[str, str]) -> Tuple[str, str]:  # type: ignore[no-redef]
        return norm_team(row.get("team") or row.get("player_team")), norm_team(row.get("opponent") or row.get("opp"))

    def parse_game_lines(payload: Any) -> List[GameLine]:  # type: ignore[no-redef]
        return []


GAME_CONTEXT_FIELDS = [
    "date", "season", "context_id", "game_id", "event_id", "team", "opponent",
    "home_team", "away_team", "venue", "source", "line_source", "line_book",
    "team_moneyline", "opponent_moneyline", "open_team_moneyline", "close_team_moneyline", "moneyline_move",
    "game_total", "open_game_total", "close_game_total", "total_move", "moneyline_implied_probability",
    "team_implied_runs", "opponent_implied_runs", "opponent_implied_runs_proxy", "implied_runs_source",
    "park_factor", "weather_temperature_f", "weather_wind_mph", "weather_wind_direction", "weather_humidity",
    "weather_precip_probability", "roof_status", "fetched_at", "readiness", "missing_fields",
]

GAME_CONTEXT_MARKET_FIELDS = [
    "date", "season", "context_id", "game_id", "team", "opponent", "market_group", "market",
    "market_display", "value", "unit", "source", "provider", "readiness", "missing_reason", "sort_order",
]

PLAYERBOARD_CONTEXT_FIELDS = [
    "game_context_id", "game_context_status", "game_context_markets", "game_context_missing",
    "game_moneyline_market", "game_total_market", "implied_runs_market",
    "team_moneyline", "opponent_moneyline", "open_team_moneyline", "close_team_moneyline", "moneyline_move",
    "game_total", "open_game_total", "close_game_total", "total_move", "moneyline_implied_probability",
    "team_implied_runs", "opponent_implied_runs", "opponent_implied_runs_proxy", "implied_runs_source",
    "game_line_source", "game_line_book", "game_line_event_id", "park_factor", "venue", "game_context_source",
    "weather_temperature_f", "weather_wind_mph", "weather_wind_direction", "weather_humidity",
    "weather_precip_probability", "roof_status",
]

CRITICAL_CONTEXT_FIELDS = ["team_moneyline", "opponent_moneyline", "game_total", "team_implied_runs", "opponent_implied_runs"]


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_csv_atomic(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp") as tmp:
        writer = csv.DictWriter(tmp, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp") as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def clean_number(value: Any) -> str:
    n = to_float(value)
    if n is None:
        return ""
    if float(n).is_integer():
        return str(int(n))
    return f"{n:.6f}".rstrip("0").rstrip(".")


def clean_percent(value: Any) -> str:
    n = to_float(value)
    if n is None:
        return ""
    return f"{n:.6f}".rstrip("0").rstrip(".")


def truthy_text(value: Any) -> str:
    return str(value or "").strip()


def context_id(date: str, team: str, opponent: str) -> str:
    material = f"{date}|{norm_team(team)}|{norm_team(opponent)}"
    return hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


def game_key(team: str, opponent: str) -> Tuple[str, str]:
    return tuple(sorted([norm_team(team), norm_team(opponent)]))


def walk_json(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_json(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)


def label_text(obj: Dict[str, Any]) -> str:
    return " ".join(str(obj.get(k, "")) for k in ("key", "market", "name", "title", "type", "label", "description")).lower()


def extract_point_from_text(value: Any) -> Optional[float]:
    text = str(value or "")
    # Common forms: Over 8.5, Total Runs 7.5, O 9, U 8
    matches = re.findall(r"(?:over|under|total|o|u)?\s*([0-9]{1,2}(?:\.[05])?)", text, flags=re.I)
    for match in matches:
        point = to_float(match)
        if point is not None and 3 <= point <= 20:
            return point
    return None


def get_outcomes(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in ("outcomes", "prices", "selections", "runners", "lines", "options"):
        value = obj.get(key)
        if isinstance(value, list):
            out.extend([x for x in value if isinstance(x, dict)])
    return out


def parse_teams_from_text(text: Any) -> Tuple[str, str]:
    s = str(text or "")
    for sep in (" @ ", " at ", " vs ", " v ", " - "):
        if sep in s:
            left, right = s.split(sep, 1)
            return norm_team(left), norm_team(right)
    return "", ""


def event_teams(obj: Dict[str, Any]) -> Tuple[str, str]:
    candidates = [
        (obj.get("away_team"), obj.get("home_team")),
        (obj.get("awayTeam"), obj.get("homeTeam")),
        (obj.get("away"), obj.get("home")),
        (obj.get("visitor"), obj.get("home")),
    ]
    for away, home in candidates:
        if away and home:
            return norm_team(away), norm_team(home)
    for key in ("game", "name", "title", "event", "description", "matchup"):
        away, home = parse_teams_from_text(obj.get(key))
        if away and home:
            return away, home
    return "", ""


def extract_total_from_event(event: Dict[str, Any]) -> Optional[float]:
    # Direct flat fields first.
    for key, value in event.items():
        nk = str(key).lower()
        if "team" in nk or "player" in nk:
            continue
        if any(token in nk for token in ("game_total", "total_runs", "total_points", "over_under", "overunder", "ou", "total")):
            point = to_float(value)
            if point is not None and 3 <= point <= 20:
                return point
            point = extract_point_from_text(value)
            if point is not None:
                return point
    # Nested total markets/outcomes.
    for obj in walk_json(event):
        text = label_text(obj)
        if "player" in text or "team total" in text:
            continue
        looks_total = any(token in text for token in ("game total", "total runs", "total points", "over under", "over/under", "totals", "total"))
        if not looks_total:
            continue
        for field in ("point", "line", "total", "value", "handicap"):
            point = to_float(obj.get(field))
            if point is not None and 3 <= point <= 20:
                return point
        for outcome in get_outcomes(obj):
            for field in ("point", "line", "total", "value", "handicap"):
                point = to_float(outcome.get(field))
                if point is not None and 3 <= point <= 20:
                    return point
            point = extract_point_from_text(" ".join(str(outcome.get(k, "")) for k in ("name", "label", "selection", "description")))
            if point is not None:
                return point
    return None


def is_moneyline_like(obj: Dict[str, Any]) -> bool:
    text = label_text(obj)
    return any(token in text for token in ("moneyline", "money line", "h2h", "head to head", "winner"))


def extract_moneylines_from_event(event: Dict[str, Any]) -> Dict[str, float]:
    moneylines: Dict[str, float] = {}
    for obj in walk_json(event):
        if not is_moneyline_like(obj):
            continue
        for outcome in get_outcomes(obj):
            name = norm_team(outcome.get("name") or outcome.get("team") or outcome.get("label") or outcome.get("selection"))
            price = to_float(outcome.get("price") or outcome.get("odds") or outcome.get("american_odds") or outcome.get("americanOdds"))
            if name and price is not None:
                moneylines[name] = price
    # Flat fallback.
    away, home = event_teams(event)
    for key, value in event.items():
        nk = str(key).lower()
        price = to_float(value)
        if price is None:
            continue
        if "away" in nk and "money" in nk and away:
            moneylines[away] = price
        elif "home" in nk and "money" in nk and home:
            moneylines[home] = price
    return moneylines


def parse_provider_game_lines(payload: Any) -> Dict[Tuple[str, str], GameLine]:
    games = {g.key: g for g in parse_game_lines(payload)}
    # v4 pass: merge totals discovered in payload shapes the v3 parser may miss.
    for event in walk_json(payload):
        away, home = event_teams(event)
        if not away or not home:
            continue
        key = tuple(sorted([away, home]))
        total = extract_total_from_event(event)
        if total is None:
            continue
        moneylines = extract_moneylines_from_event(event)
        game = games.get(key)
        if game is None:
            game = GameLine(away=away, home=home, source="provider", event_id=str(event.get("id") or event.get("event_id") or event.get("eventId") or ""))
            games[key] = game
        if total is not None and game.total is None:
            game.total = total
        for team, price in moneylines.items():
            game.moneylines.setdefault(team, price)
    return games


@dataclass
class TeamContext:
    date: str
    season: int
    team: str
    opponent: str
    home_team: str = ""
    away_team: str = ""
    venue: str = ""
    event_id: str = ""
    game_id: str = ""
    source: str = "game_context_repository"
    line_source: str = ""
    line_book: str = ""
    team_moneyline: str = ""
    opponent_moneyline: str = ""
    open_team_moneyline: str = ""
    close_team_moneyline: str = ""
    moneyline_move: str = ""
    game_total: str = ""
    open_game_total: str = ""
    close_game_total: str = ""
    total_move: str = ""
    moneyline_implied_probability: str = ""
    team_implied_runs: str = ""
    opponent_implied_runs: str = ""
    opponent_implied_runs_proxy: str = ""
    implied_runs_source: str = ""
    park_factor: str = ""
    weather_temperature_f: str = ""
    weather_wind_mph: str = ""
    weather_wind_direction: str = ""
    weather_humidity: str = ""
    weather_precip_probability: str = ""
    roof_status: str = ""
    fetched_at: str = ""

    @property
    def context_id(self) -> str:
        return context_id(self.date, self.team, self.opponent)

    @property
    def missing_fields(self) -> List[str]:
        fields = []
        for key in CRITICAL_CONTEXT_FIELDS:
            if not getattr(self, key):
                fields.append(key)
        return fields

    @property
    def readiness(self) -> str:
        if not self.team_moneyline or not self.opponent_moneyline:
            return "missing_moneyline"
        if not self.game_total:
            return "moneyline_ready_total_missing"
        if not self.team_implied_runs or not self.opponent_implied_runs:
            return "missing_implied_runs"
        return "ready"

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        row["context_id"] = self.context_id
        row["readiness"] = self.readiness
        row["missing_fields"] = "|".join(self.missing_fields)
        return row


def row_context_seed(row: Dict[str, str], date: str, season: int) -> Optional[TeamContext]:
    team, opponent = row_team_pair(row)
    if not team or not opponent:
        return None
    return TeamContext(
        date=date,
        season=season,
        team=team,
        opponent=opponent,
        home_team=norm_team(row.get("home") or row.get("home_team") or ""),
        away_team=norm_team(row.get("away") or row.get("away_team") or ""),
        venue=truthy_text(row.get("venue") or row.get("ballpark") or row.get("stadium")),
        event_id=truthy_text(row.get("event_id") or row.get("game_line_event_id")),
        game_id=truthy_text(row.get("game_id") or row.get("gamePk") or row.get("game_pk")),
        source="playerboard_join",
        line_source=truthy_text(row.get("game_line_source")),
        line_book=truthy_text(row.get("game_line_book")),
        team_moneyline=clean_number(row.get("team_moneyline")),
        opponent_moneyline=clean_number(row.get("opponent_moneyline")),
        open_team_moneyline=clean_number(row.get("open_team_moneyline")),
        close_team_moneyline=clean_number(row.get("close_team_moneyline") or row.get("team_moneyline")),
        moneyline_move=clean_number(row.get("moneyline_move")),
        game_total=clean_number(row.get("game_total")),
        open_game_total=clean_number(row.get("open_game_total")),
        close_game_total=clean_number(row.get("close_game_total") or row.get("game_total")),
        total_move=clean_number(row.get("total_move")),
        moneyline_implied_probability=clean_percent(row.get("moneyline_implied_probability")),
        team_implied_runs=clean_number(row.get("team_implied_runs")),
        opponent_implied_runs=clean_number(row.get("opponent_implied_runs")),
        opponent_implied_runs_proxy=clean_number(row.get("opponent_implied_runs_proxy")),
        implied_runs_source=truthy_text(row.get("implied_runs_source")),
        park_factor=clean_number(row.get("park_factor")),
        weather_temperature_f=clean_number(row.get("weather_temperature_f")),
        weather_wind_mph=clean_number(row.get("weather_wind_mph")),
        weather_wind_direction=truthy_text(row.get("weather_wind_direction")),
        weather_humidity=clean_number(row.get("weather_humidity")),
        weather_precip_probability=clean_number(row.get("weather_precip_probability")),
        roof_status=truthy_text(row.get("roof_status")),
    )


def merge_game_line(ctx: TeamContext, game: Optional[GameLine]) -> TeamContext:
    if game is None:
        return ctx
    team = norm_team(ctx.team)
    opp = norm_team(ctx.opponent)
    team_ml = game.moneylines.get(team)
    opp_ml = game.moneylines.get(opp)
    if team_ml is not None:
        ctx.team_moneyline = clean_number(team_ml)
        ctx.close_team_moneyline = ctx.close_team_moneyline or ctx.team_moneyline
        prob = moneyline_to_probability(team_ml)
        ctx.moneyline_implied_probability = clean_percent(prob)
    if opp_ml is not None:
        ctx.opponent_moneyline = clean_number(opp_ml)
    if game.total is not None:
        ctx.game_total = clean_number(game.total)
        ctx.close_game_total = ctx.close_game_total or ctx.game_total
    total = to_float(ctx.game_total)
    tml = to_float(ctx.team_moneyline)
    oml = to_float(ctx.opponent_moneyline)
    team_runs, opp_runs = implied_runs_proxy(total, tml, oml)
    if team_runs is not None and opp_runs is not None:
        ctx.team_implied_runs = clean_number(team_runs)
        ctx.opponent_implied_runs = clean_number(opp_runs)
        ctx.opponent_implied_runs_proxy = clean_number(opp_runs)
        ctx.implied_runs_source = "moneyline_total_proxy"
    ctx.line_source = ctx.line_source or getattr(game, "source", "provider") or "provider"
    ctx.line_book = ctx.line_book or getattr(game, "book", "") or "provider"
    ctx.event_id = ctx.event_id or getattr(game, "event_id", "")
    return ctx


def prefer_context(existing: TeamContext, candidate: TeamContext) -> TeamContext:
    # Merge values into the existing canonical context without overwriting real data with blanks.
    for field_name in GAME_CONTEXT_FIELDS:
        if field_name in {"date", "season", "context_id", "readiness", "missing_fields", "fetched_at"}:
            continue
        current = getattr(existing, field_name, "") if hasattr(existing, field_name) else ""
        new = getattr(candidate, field_name, "") if hasattr(candidate, field_name) else ""
        if not current and new:
            setattr(existing, field_name, new)
    return existing


def build_contexts(rows: Sequence[Dict[str, str]], games_by_key: Dict[Tuple[str, str], GameLine], date: str, season: int, markets: Sequence[str]) -> Dict[str, TeamContext]:
    market_set = {m for m in markets if m}
    contexts: Dict[str, TeamContext] = {}
    fetched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for row in rows:
        if row_date(row) != date:
            continue
        if market_set and row_market(row) not in market_set:
            continue
        seed = row_context_seed(row, date, season)
        if not seed:
            continue
        seed.fetched_at = fetched_at
        key = game_key(seed.team, seed.opponent)
        seed = merge_game_line(seed, games_by_key.get(key))
        cid = seed.context_id
        if cid in contexts:
            prefer_context(contexts[cid], seed)
            # A second merge after prefer fills implied runs when total arrived from another row.
            merge_game_line(contexts[cid], games_by_key.get(key))
        else:
            contexts[cid] = seed
    return contexts


def market_ready(value: Any) -> str:
    return "ready" if truthy_text(value) else "missing"


def context_market_rows(contexts: Dict[str, TeamContext]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    specs = [
        ("game_moneyline", "Team Moneyline", "team_moneyline", "american", 10),
        ("opponent_moneyline", "Opponent Moneyline", "opponent_moneyline", "american", 20),
        ("moneyline_implied_probability", "Moneyline Implied Probability", "moneyline_implied_probability", "probability", 30),
        ("game_total", "Game Total", "game_total", "runs", 40),
        ("team_implied_runs", "Team Implied Runs", "team_implied_runs", "runs", 50),
        ("opponent_implied_runs", "Opponent Implied Runs", "opponent_implied_runs", "runs", 60),
    ]
    for ctx in sorted(contexts.values(), key=lambda c: (c.team, c.opponent)):
        for market, display, attr, unit, order in specs:
            value = getattr(ctx, attr)
            readiness = market_ready(value)
            rows.append({
                "date": ctx.date,
                "season": ctx.season,
                "context_id": ctx.context_id,
                "game_id": ctx.game_id,
                "team": ctx.team,
                "opponent": ctx.opponent,
                "market_group": "game_context",
                "market": market,
                "market_display": display,
                "value": value,
                "unit": unit,
                "source": ctx.line_source or ctx.source,
                "provider": ctx.line_book or "",
                "readiness": readiness,
                "missing_reason": "" if readiness == "ready" else f"{market} missing from game context provider",
                "sort_order": order,
            })
    return rows


def markers_for_context(ctx: TeamContext) -> Tuple[str, str, str, str]:
    moneyline = "ready" if ctx.team_moneyline and ctx.opponent_moneyline else "missing"
    total = "ready" if ctx.game_total else "missing"
    implied = "ready" if ctx.team_implied_runs and ctx.opponent_implied_runs else "missing"
    status = "ready" if moneyline == total == implied == "ready" else "partial" if moneyline == "ready" else "missing"
    return moneyline, total, implied, status


def enrich_playerboard_rows(rows: List[Dict[str, str]], contexts: Dict[str, TeamContext], date: str, markets: Sequence[str]) -> Dict[str, Any]:
    market_set = {m for m in markets if m}
    target = matched = updated = 0
    missing_context = 0
    for row in rows:
        if row_date(row) != date:
            continue
        if market_set and row_market(row) not in market_set:
            continue
        target += 1
        team, opponent = row_team_pair(row)
        if not team or not opponent:
            missing_context += 1
            continue
        cid = context_id(date, team, opponent)
        ctx = contexts.get(cid)
        if not ctx:
            missing_context += 1
            continue
        matched += 1
        before = json.dumps({k: row.get(k, "") for k in PLAYERBOARD_CONTEXT_FIELDS}, sort_keys=True)
        ctx_row = ctx.to_row()
        row["game_context_id"] = ctx.context_id
        moneyline, total, implied, status = markers_for_context(ctx)
        row["game_context_status"] = status
        row["game_context_markets"] = f"moneyline:{moneyline};game_total:{total};implied_runs:{implied}"
        row["game_context_missing"] = "|".join(ctx.missing_fields)
        row["game_moneyline_market"] = moneyline
        row["game_total_market"] = total
        row["implied_runs_market"] = implied
        mapping = {
            "team_moneyline": "team_moneyline",
            "opponent_moneyline": "opponent_moneyline",
            "open_team_moneyline": "open_team_moneyline",
            "close_team_moneyline": "close_team_moneyline",
            "moneyline_move": "moneyline_move",
            "game_total": "game_total",
            "open_game_total": "open_game_total",
            "close_game_total": "close_game_total",
            "total_move": "total_move",
            "moneyline_implied_probability": "moneyline_implied_probability",
            "team_implied_runs": "team_implied_runs",
            "opponent_implied_runs": "opponent_implied_runs",
            "opponent_implied_runs_proxy": "opponent_implied_runs_proxy",
            "implied_runs_source": "implied_runs_source",
            "game_line_source": "line_source",
            "game_line_book": "line_book",
            "game_line_event_id": "event_id",
            "park_factor": "park_factor",
            "venue": "venue",
            "game_context_source": "source",
            "weather_temperature_f": "weather_temperature_f",
            "weather_wind_mph": "weather_wind_mph",
            "weather_wind_direction": "weather_wind_direction",
            "weather_humidity": "weather_humidity",
            "weather_precip_probability": "weather_precip_probability",
            "roof_status": "roof_status",
        }
        for target_field, context_field in mapping.items():
            value = ctx_row.get(context_field, "")
            if value != "":
                row[target_field] = str(value)
        after = json.dumps({k: row.get(k, "") for k in PLAYERBOARD_CONTEXT_FIELDS}, sort_keys=True)
        if after != before:
            updated += 1
    return {"targetRows": target, "matchedRows": matched, "updatedRows": updated, "missingContextRows": missing_context}


def load_game_lines(date: str) -> Dict[Tuple[str, str], GameLine]:
    path = GAME_CONTEXT_DIR / f"game_lines_{date}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_provider_game_lines(payload)


def build_game_context_markets(date: str, season: int, markets: Sequence[str], dry_run: bool = False) -> Dict[str, Any]:
    playerboard_path = PLAYERBOARD_DIR / f"playerboard_{season}.csv"
    if not playerboard_path.exists():
        raise FileNotFoundError(playerboard_path)
    rows = read_csv(playerboard_path)
    original_fields = list(rows[0].keys()) if rows else []
    games_by_key = load_game_lines(date)
    contexts = build_contexts(rows, games_by_key, date, season, markets)
    context_rows = [ctx.to_row() for ctx in contexts.values()]
    market_rows = context_market_rows(contexts)
    enrich_summary = enrich_playerboard_rows(rows, contexts, date, markets)

    context_path = GAME_CONTEXT_DIR / f"game_context_{date}.csv"
    market_path = GAME_CONTEXT_DIR / f"game_context_markets_{date}.csv"
    audit_path = AUDIT_DIR / f"phase17_v4_game_context_markets_{date}.json"

    fieldnames = list(original_fields)
    for field_name in PLAYERBOARD_CONTEXT_FIELDS:
        if field_name not in fieldnames:
            fieldnames.append(field_name)

    if not dry_run:
        write_csv_atomic(context_path, GAME_CONTEXT_FIELDS, context_rows)
        write_csv_atomic(market_path, GAME_CONTEXT_MARKET_FIELDS, market_rows)
        write_csv_atomic(playerboard_path, fieldnames, rows)

    totals_ready = sum(1 for c in contexts.values() if c.game_total)
    implied_ready = sum(1 for c in contexts.values() if c.team_implied_runs and c.opponent_implied_runs)
    moneylines_ready = sum(1 for c in contexts.values() if c.team_moneyline and c.opponent_moneyline)
    audit = {
        "status": "ok" if contexts else "warning",
        "date": date,
        "season": season,
        "markets": list(markets),
        "playerboardPath": str(playerboard_path),
        "gameLinesPath": str(GAME_CONTEXT_DIR / f"game_lines_{date}.json"),
        "gameContextPath": str(context_path),
        "gameContextMarketsPath": str(market_path),
        "contexts": len(contexts),
        "marketRows": len(market_rows),
        "providerGames": len(games_by_key),
        "providerGamesWithMoneyline": sum(1 for g in games_by_key.values() if g.moneylines),
        "providerGamesWithTotal": sum(1 for g in games_by_key.values() if g.total is not None),
        "contextsWithMoneyline": moneylines_ready,
        "contextsWithTotal": totals_ready,
        "contextsWithImpliedRuns": implied_ready,
        "enrichment": enrich_summary,
        "missingCriticalByContext": {cid: ctx.missing_fields for cid, ctx in contexts.items() if ctx.missing_fields},
        "dryRun": dry_run,
    }
    if not dry_run:
        write_json(audit_path, audit)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical game-context market rows and enrich Playerboard.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--markets", nargs="*", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_game_context_markets(args.date, args.season, args.markets, args.dry_run), indent=2))


if __name__ == "__main__":
    main()
