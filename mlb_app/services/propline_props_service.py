from __future__ import annotations

import csv
import os
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

DEFAULT_DAILY_RESERVE = 150
DEFAULT_MAX_DAILY_PULL_REQUESTS = 750


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
    snapshot_id: str = ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _validate_date(date_label: str) -> str:
    value = _clean(date_label)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise PropLineSyncError("PropLine date must be YYYY-MM-DD.")
    return value


def _local_timezone() -> ZoneInfo | timezone:
    try:
        return ZoneInfo(PROPLINE_LOCAL_TZ)
    except Exception:
        return timezone.utc


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


def save_props_csv(
    props: list[dict[str, Any]],
    date_label: str,
    *,
    snapshot: bool = True,
    snapshot_id: str = "",
) -> dict[str, Any]:
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
        stamp = _clean(snapshot_id) or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_file = WAREHOUSE_SNAPSHOT_DIR / f"propline_props_{date_label}_{stamp}.csv"
        shutil.copyfile(path, snapshot_file)
        snapshot_path = str(snapshot_file)

    return {"savedPath": str(path), "snapshotPath": snapshot_path, "rowCount": len(props)}


def sync_propline_props(request: PropLineSyncRequest) -> dict[str, Any]:
    date_label = _validate_date(request.date)
    requested_markets = tuple(market.strip() for market in request.markets if str(market).strip()) or tuple(PROPLINE_MARKETS)

    try:
        from mlb_app.integrations.propline.client import get_events, get_event_player_props, value_client_status
    except Exception as error:  # pragma: no cover - import environment dependent
        raise PropLineSyncError(f"Could not import PropLine client helpers: {error}") from error

    full_slate_pull_enabled = _env_flag("MLB_PROPLINE_FULL_SLATE_PULL", True)
    include_all_books_enabled = _env_flag("MLB_PROPLINE_INCLUDE_ALL_BOOKS", True)
    include_alt_lines_enabled = _env_flag("MLB_PROPLINE_INCLUDE_ALT_LINES", False)
    max_daily_pull_requests = _env_int("MLB_PROPLINE_MAX_DAILY_PULL_REQUESTS", DEFAULT_MAX_DAILY_PULL_REQUESTS)
    reserved_requests = _env_int("MLB_PROPLINE_DAILY_RESERVE", DEFAULT_DAILY_RESERVE)
    markets = requested_markets if include_alt_lines_enabled else tuple(
        market for market in requested_markets if not re.search(r"(?:_alt|_\d+plus_)", market)
    )

    all_events = get_events(request.sport)
    events = [event for event in all_events if not event_date(event) or event_date(event) == date_label]
    if not full_slate_pull_enabled:
        events = events[:1]
    if request.max_events and request.max_events > 0:
        events = events[: request.max_events]

    token_guard_before: dict[str, Any] = {}
    try:
        token_guard_before = value_client_status().get("tokenGuard", {})
    except Exception:
        token_guard_before = {}
    usable_remaining_before = int(token_guard_before.get("remainingUsable") or 0)
    event_budget = max(0, min(max_daily_pull_requests, usable_remaining_before))

    props: list[dict[str, Any]] = []
    event_errors: list[dict[str, Any]] = []
    empty_events: list[dict[str, Any]] = []
    event_summaries: list[dict[str, Any]] = []
    attempted_events = 0
    skipped_budget_events: list[dict[str, Any]] = []

    for event in events:
        event_id = _clean(event.get("id"))
        if not event_id:
            continue
        if attempted_events >= event_budget:
            skipped_budget_events.append({
                "eventId": event_id,
                "game": f"{event.get('away_team', '')} @ {event.get('home_team', '')}".strip(),
                "reason": "propline_request_budget_exhausted",
            })
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
        if not include_all_books_enabled and bookmakers:
            bookmakers = bookmakers[:1]
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

    saved = save_props_csv(
        props,
        date_label,
        snapshot=request.snapshot,
        snapshot_id=request.snapshot_id,
    ) if request.save else {"savedPath": "", "snapshotPath": "", "rowCount": len(props)}

    warnings: list[str] = []
    if not events and all_events:
        warnings.append(f"PropLine returned {len(all_events)} total events, but none matched {date_label} in {PROPLINE_LOCAL_TZ}.")
    if events and not props and not event_errors:
        warnings.append("PropLine returned events, but no outcomes for the selected player-prop markets. Try fewer markets or check event market availability.")
    if not all_events:
        warnings.append("PropLine returned no events; source unavailable, API issue, or no slate for the selected sport.")
    if event_errors:
        warnings.append(f"{len(event_errors)} PropLine event calls failed; returned props from successful events only.")
    if skipped_budget_events:
        warnings.append(f"{len(skipped_budget_events)} PropLine events skipped before violating daily reserve/request budget.")

    token_guard = {}
    try:
        token_guard = value_client_status().get("tokenGuard", {})
    except Exception:
        token_guard = {}

    markets_returned = sorted({_clean(prop.get("market")) for prop in props if _clean(prop.get("market"))})
    books_returned = sorted({_clean(prop.get("book") or prop.get("bookKey")) for prop in props if _clean(prop.get("book") or prop.get("bookKey"))})
    raw_book_quote_keys = {
        (
            _clean(prop.get("eventId")),
            _clean(prop.get("market")),
            _clean(prop.get("player")).casefold(),
            _clean(prop.get("side")).casefold(),
            _clean(prop.get("line")),
            _clean(prop.get("bookKey") or prop.get("book")).casefold(),
        )
        for prop in props
    }

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
        "diagnostics": {
            "proplineRequestsUsed": int(token_guard.get("estimatedUsed") or 0),
            "proplineDailyLimit": int(token_guard.get("dailyLimit") or 0),
            "proplineReservedRequests": reserved_requests,
            "proplineUsableRemaining": int(token_guard.get("remainingUsable") or 0),
            "proplineMaxDailyPullRequests": max_daily_pull_requests,
            "fullSlatePullEnabled": full_slate_pull_enabled,
            "includeAllBooksEnabled": include_all_books_enabled,
            "includeAltLinesEnabled": include_alt_lines_enabled,
            "eventsDiscovered": len(events),
            "totalEventCount": len(all_events),
            "eventsAttempted": attempted_events,
            "eventsSkipped": len(skipped_budget_events),
            "marketsRequested": list(markets),
            "marketsReturned": markets_returned,
            "booksReturned": books_returned,
            "rawPropsReturned": len(props),
            "rawBookQuotesReturned": len(raw_book_quote_keys),
            "propsDroppedBeforePlayerboard": 0,
            "propsDroppedByMarket": {},
            "propsDroppedByMissingOdds": sum(1 for prop in props if not _clean(prop.get("americanOdds"))),
            "propsDroppedByMissingPlayer": sum(1 for prop in props if not _clean(prop.get("player"))),
            "propsDroppedByUnsupportedSide": 0,
            "propsDroppedByDuplicateCollapse": max(0, len(props) - len(raw_book_quote_keys)),
            "propsLoadedIntoPlayerboard": 0,
            "boardRowsGenerated": 0,
            "bookQuotesGenerated": len(raw_book_quote_keys),
            "marketRegistryRowsGenerated": 0,
        },
        "savedPath": saved.get("savedPath", ""),
        "snapshotPath": saved.get("snapshotPath", ""),
        "warnings": warnings,
        "eventErrors": event_errors[:20],
        "emptyEvents": empty_events[:20],
        "skippedEvents": skipped_budget_events[:20],
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
