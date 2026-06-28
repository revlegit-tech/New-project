from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings

NORMALIZED_GAME_MARKET_FIELDS = (
    "date",
    "season",
    "event_id",
    "game_id",
    "source",
    "source_event_id",
    "source_market_key",
    "book",
    "home_team",
    "away_team",
    "team",
    "opponent",
    "market",
    "side",
    "line",
    "american_odds",
    "implied_probability",
    "last_update",
    "snapshot_at",
    "is_live",
    "raw_source",
)

CANONICAL_GAME_MARKET_FIELDS = (
    "date",
    "season",
    "game_id",
    "game_pk",
    "home_team",
    "away_team",
    "team",
    "opponent",
    "market_type",
    "open_moneyline",
    "current_moneyline",
    "open_total",
    "current_total",
    "open_run_line",
    "current_run_line",
    "team_total",
    "no_vig_win_prob_open",
    "no_vig_win_prob_current",
    "line_movement",
    "book_count_moneyline",
    "book_count_total",
    "book_count_runline",
    "source",
    "source_snapshot_at",
    "quality_flags",
)

CANONICAL_GAME_MARKETS = {
    "h2h": "moneyline",
    "moneyline": "moneyline",
    "money_line": "moneyline",
    "spreads": "run_line",
    "spread": "run_line",
    "run_line": "run_line",
    "runline": "run_line",
    "totals": "game_total",
    "total": "game_total",
    "game_total": "game_total",
    "team_totals": "team_total",
    "team_total": "team_total",
    "alternate_spreads": "alt_run_line",
    "alt_run_line": "alt_run_line",
    "alternate_totals": "alt_game_total",
    "alt_game_total": "alt_game_total",
}


class GameMarketContextService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def normalized_path(self, date_label: str) -> Path:
        return self.settings.data_dir / "warehouse" / "normalized" / "game_markets" / f"game_markets_{date_label}.csv"

    def read_rows(self, date_label: str) -> list[dict[str, str]]:
        path = self.normalized_path(date_label)
        if not path.is_file():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def context_by_team(self, *, date_label: str, team: str, opponent: str) -> dict[str, Any]:
        rows = self.read_rows(date_label)
        team_key = _team_key(team)
        opp_key = _team_key(opponent)
        matched = [
            row for row in rows
            if _team_key(row.get("team")) == team_key and _team_key(row.get("opponent")) == opp_key
        ]
        return _context_payload(date_label=date_label, team=team, opponent=opponent, rows=matched, artifact_exists=bool(rows))

    def context_by_game_id(self, *, date_label: str, game_id: str) -> dict[str, Any]:
        rows = self.read_rows(date_label)
        matched = [
            row for row in rows
            if str(row.get("game_id") or row.get("event_id") or row.get("source_event_id") or "") == str(game_id)
        ]
        team = matched[0].get("team", "") if matched else ""
        opponent = matched[0].get("opponent", "") if matched else ""
        return _context_payload(date_label=date_label, team=team, opponent=opponent, rows=matched, artifact_exists=bool(rows))


def normalize_game_market_payload(
    payload: Any,
    *,
    date_label: str,
    season: int,
    source: str = "provider",
    raw_source: str = "",
    snapshot_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot = snapshot_at or datetime.now(timezone.utc).isoformat()
    events = _event_list(payload)
    rows: list[dict[str, Any]] = []
    missing_team_total_games = 0
    games_seen = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        home = _clean(event.get("home_team") or event.get("homeTeam") or event.get("home"))
        away = _clean(event.get("away_team") or event.get("awayTeam") or event.get("away"))
        if not home or not away:
            continue
        games_seen += 1
        event_id = _clean(event.get("id") or event.get("event_id") or event.get("eventId") or event.get("game_id") or event.get("gamePk"))
        event_rows_before = len(rows)
        team_total_found = False
        for book in event.get("bookmakers", []) or event.get("books", []) or [{"markets": event.get("markets", [])}]:
            if not isinstance(book, dict):
                continue
            book_name = _clean(book.get("title") or book.get("key") or book.get("book") or book.get("sportsbook"))
            last_update = _clean(book.get("last_update") or book.get("lastUpdate") or event.get("last_update") or event.get("commence_time"))
            for market in book.get("markets", []) or []:
                if not isinstance(market, dict):
                    continue
                market_key = _clean(market.get("key") or market.get("market") or market.get("type")).lower()
                canonical = CANONICAL_GAME_MARKETS.get(market_key)
                if not canonical:
                    continue
                if canonical == "team_total":
                    team_total_found = True
                for outcome in market.get("outcomes", []) or market.get("selections", []) or []:
                    if not isinstance(outcome, dict):
                        continue
                    rows.append(
                        _row_from_outcome(
                            outcome,
                            date_label=date_label,
                            season=season,
                            event_id=event_id,
                            source=source,
                            source_market_key=market_key,
                            book=book_name,
                            home_team=home,
                            away_team=away,
                            market=canonical,
                            last_update=last_update,
                            snapshot_at=snapshot,
                            raw_source=raw_source,
                            is_live=bool(event.get("is_live") or event.get("live")),
                        )
                    )
        if len(rows) > event_rows_before and not team_total_found:
            missing_team_total_games += 1
    summary = {
        "status": "ok" if rows and missing_team_total_games == 0 else "partial" if rows else "missing",
        "date": date_label,
        "season": season,
        "gamesSeen": games_seen,
        "rowCount": len(rows),
        "missingTeamTotalGames": missing_team_total_games,
        "teamTotalsAvailable": missing_team_total_games == 0 and bool(rows),
    }
    return rows, summary


def write_normalized_game_markets(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(CANONICAL_GAME_MARKET_FIELDS) if rows and "market_type" in rows[0] else list(NORMALIZED_GAME_MARKET_FIELDS)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def normalize_game_market_file(input_path: Path, output_path: Path, *, date_label: str, season: int, source: str = "") -> dict[str, Any]:
    payload: Any
    if input_path.suffix.lower() == ".json":
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            payload = {"events": list(csv.DictReader(handle))}
    rows, summary = normalize_game_market_payload(
        payload,
        date_label=date_label,
        season=season,
        source=source or input_path.stem,
        raw_source=str(input_path),
    )
    write_normalized_game_markets(output_path, rows)
    summary["outputPath"] = str(output_path)
    return summary


def _event_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("events", "data", "results", "games"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _row_from_outcome(
    outcome: dict[str, Any],
    *,
    date_label: str,
    season: int,
    event_id: str,
    source: str,
    source_market_key: str,
    book: str,
    home_team: str,
    away_team: str,
    market: str,
    last_update: str,
    snapshot_at: str,
    raw_source: str,
    is_live: bool,
) -> dict[str, Any]:
    side = _clean(outcome.get("name") or outcome.get("label") or outcome.get("selection") or outcome.get("side"))
    team = _team_for_side(side, home_team=home_team, away_team=away_team)
    opponent = away_team if _team_key(team) == _team_key(home_team) else home_team if team else ""
    odds = _clean(outcome.get("price") or outcome.get("americanOdds") or outcome.get("american_odds") or outcome.get("odds"))
    line = _clean(outcome.get("point") or outcome.get("line") or outcome.get("total") or outcome.get("handicap"))
    return {
        "date": date_label,
        "season": season,
        "event_id": event_id,
        "game_id": event_id,
        "source": source,
        "source_event_id": event_id,
        "source_market_key": source_market_key,
        "book": book,
        "home_team": home_team,
        "away_team": away_team,
        "team": team,
        "opponent": opponent,
        "market": market,
        "side": side,
        "line": line,
        "american_odds": odds,
        "implied_probability": _implied_probability(odds),
        "last_update": last_update,
        "snapshot_at": snapshot_at,
        "is_live": str(bool(is_live)).lower(),
        "raw_source": raw_source,
    }


def _context_payload(*, date_label: str, team: str, opponent: str, rows: list[dict[str, str]], artifact_exists: bool) -> dict[str, Any]:
    by_market: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_market.setdefault(str(row.get("market_type") or row.get("market") or ""), []).append(row)
    source_status = "missing"
    if rows:
        source_status = "ok" if by_market.get("moneyline") and by_market.get("game_total") and by_market.get("team_total") else "partial"
    elif artifact_exists:
        source_status = "partial"
    latest = max((str(row.get("snapshot_at") or row.get("last_update") or "") for row in rows), default="")
    return {
        "date": date_label,
        "team": team,
        "opponent": opponent,
        "moneyline": _first_market(by_market, "moneyline"),
        "runLine": _first_market(by_market, "run_line"),
        "gameTotal": _first_market(by_market, "game_total"),
        "teamTotal": _first_market(by_market, "team_total"),
        "freshness": {"latest": latest, "rowCount": len(rows)},
        "sourceStatus": source_status,
    }


def _first_market(by_market: dict[str, list[dict[str, str]]], key: str) -> dict[str, str]:
    row = dict((by_market.get(key) or [{}])[0])
    if row and "market_type" in row:
        row.setdefault("market", row.get("market_type", ""))
        if key == "game_total":
            row.setdefault("line", row.get("current_total", ""))
        elif key == "run_line":
            row.setdefault("line", row.get("current_run_line", ""))
        elif key == "team_total":
            row.setdefault("line", row.get("team_total", ""))
        elif key == "moneyline":
            row.setdefault("implied_probability", row.get("no_vig_win_prob_current", ""))
        row.setdefault("snapshot_at", row.get("source_snapshot_at", ""))
    return row


def _team_for_side(side: str, *, home_team: str, away_team: str) -> str:
    key = _team_key(side)
    if key in {"home", _team_key(home_team)}:
        return home_team
    if key in {"away", _team_key(away_team)}:
        return away_team
    if side.lower() in {"over", "under"}:
        return ""
    return side


def _implied_probability(value: Any) -> str:
    try:
        odds = float(str(value).replace("+", "").strip())
    except Exception:
        return ""
    if not math.isfinite(odds) or odds == 0:
        return ""
    probability = 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)
    return f"{probability:.6f}".rstrip("0").rstrip(".")


def _team_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _clean(value: Any) -> str:
    return str(value or "").strip()
