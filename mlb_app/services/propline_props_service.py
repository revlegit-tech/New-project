from __future__ import annotations

import csv
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"
WAREHOUSE_SNAPSHOT_DIR = DATA_DIR / "warehouse" / "odds_snapshots"

PROPLINE_SPORT = "baseball_mlb"
PROPLINE_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "batter_rbis",
    "batter_stolen_bases",
    "batter_walks",
    "batter_singles",
    "batter_doubles",
    "batter_runs",
    "batter_2plus_hits",
    "batter_2plus_home_runs",
    "batter_2plus_rbis",
    "batter_3plus_rbis",
    "pitcher_strikeouts",
    "pitcher_outs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]
PROPLINE_LOCAL_TZ = "America/New_York"

PROP_COLUMNS = [
    "date",
    "eventDateLocal",
    "commenceTime",
    "eventId",
    "game",
    "homeTeam",
    "awayTeam",
    "team",
    "opponent",
    "book",
    "bookKey",
    "market",
    "player",
    "side",
    "line",
    "americanOdds",
    "lastUpdate",
]


class PropLineSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class PropLineSyncRequest:
    date: str
    sport: str = PROPLINE_SPORT
    markets: tuple[str, ...] = tuple(PROPLINE_MARKETS)
    save: bool = True
    snapshot: bool = True
    max_events: int = 0


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _validate_date(date_label: str) -> str:
    value = _clean(date_label)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise PropLineSyncError("PropLine date must be YYYY-MM-DD.")
    return value


def _local_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(PROPLINE_LOCAL_TZ)
    except Exception:
        return ZoneInfo("America/New_York")


def _event_datetime(event: dict[str, Any]) -> datetime | None:
    raw = _clean(event.get("commence_time") or event.get("commenceTime") or event.get("date"))
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_local_timezone())


def event_date(event: dict[str, Any]) -> str:
    local_dt = _event_datetime(event)
    if local_dt:
        return local_dt.strftime("%Y-%m-%d")
    raw = _clean(event.get("commence_time") or event.get("commenceTime") or event.get("date"))
    return raw[:10] if re.match(r"\d{4}-\d{2}-\d{2}", raw) else ""


def _split_player_and_team(value: Any) -> tuple[str, str]:
    text = _clean(value)
    match = re.match(r"^(?P<player>.+?)\s+\((?P<team>[A-Z]{2,4})\)$", text)
    if not match:
        return text, ""
    return match.group("player").strip(), match.group("team").strip()


def normalize_prop(event: dict[str, Any], bookmaker: dict[str, Any], market: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    player, team = _split_player_and_team(outcome.get("description") or outcome.get("player") or "")
    local_dt = _event_datetime(event)
    commence_time = event.get("commence_time") or event.get("commenceTime") or event.get("date") or ""
    return {
        "date": commence_time,
        "eventDateLocal": local_dt.strftime("%Y-%m-%d") if local_dt else event_date(event),
        "commenceTime": commence_time,
        "eventId": event.get("id", ""),
        "game": f"{event.get('away_team', '')} @ {event.get('home_team', '')}".strip(),
        "homeTeam": event.get("home_team", ""),
        "awayTeam": event.get("away_team", ""),
        "team": team,
        "opponent": "",
        "book": bookmaker.get("title") or bookmaker.get("key") or "",
        "bookKey": bookmaker.get("key", ""),
        "market": market.get("key", ""),
        "player": player,
        "side": outcome.get("name", ""),
        "line": outcome.get("point", ""),
        "americanOdds": outcome.get("price", ""),
        "lastUpdate": market.get("last_update") or bookmaker.get("last_update") or "",
    }


def save_props_csv(props: list[dict[str, Any]], date_label: str, *, snapshot: bool = True) -> dict[str, Any]:
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    path = ODDS_DIR / f"propline_props_{date_label}.csv"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROP_COLUMNS)
        writer.writeheader()
        for prop in props:
            writer.writerow({column: prop.get(column, "") for column in PROP_COLUMNS})
    tmp_path.replace(path)

    snapshot_path = ""
    if snapshot:
        WAREHOUSE_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_file = WAREHOUSE_SNAPSHOT_DIR / f"propline_props_{date_label}_{stamp}.csv"
        shutil.copyfile(path, snapshot_file)
        snapshot_path = str(snapshot_file)

    return {"savedPath": str(path), "snapshotPath": snapshot_path, "rowCount": len(props)}


def sync_propline_props(request: PropLineSyncRequest) -> dict[str, Any]:
    date_label = _validate_date(request.date)
    markets = tuple(market.strip() for market in request.markets if str(market).strip()) or tuple(PROPLINE_MARKETS)

    try:
        from mlb_app.integrations.propline.client import get_events, get_event_player_props, value_client_status
    except Exception as error:  # pragma: no cover - import environment dependent
        raise PropLineSyncError(f"Could not import PropLine client helpers: {error}") from error

    all_events = get_events(request.sport)
    events = [event for event in all_events if not event_date(event) or event_date(event) == date_label]
    if request.max_events and request.max_events > 0:
        events = events[: request.max_events]

    props: list[dict[str, Any]] = []
    event_errors: list[dict[str, Any]] = []
    empty_events: list[dict[str, Any]] = []
    event_summaries: list[dict[str, Any]] = []
    attempted_events = 0

    for event in events:
        event_id = _clean(event.get("id"))
        if not event_id:
            continue
        attempted_events += 1
        try:
            odds = get_event_player_props(event_id, markets=list(markets), sport=request.sport)
        except Exception as error:  # noqa: BLE001 - explicit per-event diagnostic
            event_errors.append({
                "eventId": event_id,
                "game": f"{event.get('away_team', '')} @ {event.get('home_team', '')}".strip(),
                "commenceTime": event.get("commence_time") or event.get("commenceTime") or event.get("date") or "",
                "error": str(error),
            })
            continue

        bookmakers = odds.get("bookmakers", []) if isinstance(odds, dict) else []
        event_prop_count = 0
        market_counts: dict[str, int] = {}
        for bookmaker in bookmakers or []:
            for market in bookmaker.get("markets", []) or []:
                market_key = _clean(market.get("key"))
                outcomes = market.get("outcomes", []) or []
                market_counts[market_key] = market_counts.get(market_key, 0) + len(outcomes)
                for outcome in outcomes:
                    props.append(normalize_prop(event, bookmaker, market, outcome))
                    event_prop_count += 1

        summary = {
            "eventId": event_id,
            "game": f"{event.get('away_team', '')} @ {event.get('home_team', '')}".strip(),
            "eventDateLocal": event_date(event),
            "commenceTime": event.get("commence_time") or event.get("commenceTime") or event.get("date") or "",
            "bookmakers": len(bookmakers or []),
            "props": event_prop_count,
            "markets": market_counts,
        }
        event_summaries.append(summary)
        if event_prop_count == 0:
            empty_events.append(summary)

    if attempted_events and len(event_errors) == attempted_events:
        first = event_errors[0]["error"] if event_errors else "unknown error"
        raise PropLineSyncError(f"PropLine player-prop calls failed for all {attempted_events} events. First error: {first}")

    saved = save_props_csv(props, date_label, snapshot=request.snapshot) if request.save else {"savedPath": "", "snapshotPath": "", "rowCount": len(props)}

    warnings: list[str] = []
    if not events and all_events:
        warnings.append(f"PropLine returned {len(all_events)} total events, but none matched {date_label} in {PROPLINE_LOCAL_TZ}.")
    if events and not props and not event_errors:
        warnings.append("PropLine returned events, but no outcomes for the selected player-prop markets. Try fewer markets or check event market availability.")
    if event_errors:
        warnings.append(f"{len(event_errors)} PropLine event calls failed; returned props from successful events only.")

    token_guard = {}
    try:
        token_guard = value_client_status().get("tokenGuard", {})
    except Exception:
        token_guard = {}

    return {
        "status": "ok",
        "date": date_label,
        "sport": request.sport,
        "timezone": PROPLINE_LOCAL_TZ,
        "markets": list(markets),
        "eventCount": len(events),
        "totalEventCount": len(all_events),
        "attemptedEventCount": attempted_events,
        "maxEvents": request.max_events,
        "propCount": len(props),
        "savedPath": saved.get("savedPath", ""),
        "snapshotPath": saved.get("snapshotPath", ""),
        "warnings": warnings,
        "eventErrors": event_errors[:20],
        "emptyEvents": empty_events[:20],
        "eventsPreview": event_summaries[:20],
        "tokenGuard": token_guard,
    }


class ProplinePropsService:
    """Application-scoped service wrapper for PropLine admin syncs.

    The sync implementation remains a module function for CLI compatibility,
    but native FastAPI routes depend on this class through AppContainer so the
    production request path has one dependency-injection story.
    """

    def sync(self, request: PropLineSyncRequest) -> dict[str, Any]:
        return sync_propline_props(request)
