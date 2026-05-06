from __future__ import annotations
from local_env import load_local_env
load_local_env()

import os
from typing import Any

from propline_token_guard import can_spend, guard_summary, record_call

SPORT = "baseball_mlb"

PLAYER_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "batter_rbis",
    "batter_stolen_bases",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]

GAME_MARKETS = ["h2h", "spreads", "totals"]


class PropLineBudgetError(RuntimeError):
    pass


class PropLineUnavailableError(RuntimeError):
    pass


def client() -> Any:
    api_key = os.environ.get("PROPLINE_API_KEY", "").strip()
    if not api_key:
        raise PropLineUnavailableError("Missing PROPLINE_API_KEY.")

    try:
        from propline import PropLine
    except Exception as error:
        raise PropLineUnavailableError("Install PropLine first: python -m pip install propline") from error

    return PropLine(api_key)


def guarded_call(label: str, fn, *, cost: int = 1, essential: bool = True, meta: dict[str, Any] | None = None):
    if not essential and not can_spend(cost):
        raise PropLineBudgetError(f"Skipping nonessential PropLine call due to token guard: {label}")

    if essential and not can_spend(cost):
        raise PropLineBudgetError(f"PropLine token guard blocked essential call: {label}")

    try:
        result = fn()
        record_call(label, cost=cost, ok=True, meta=meta)
        return result
    except Exception as error:
        record_call(label, cost=cost, ok=False, meta={**(meta or {}), "error": str(error)})
        raise


def get_events(sport: str = SPORT) -> list[dict[str, Any]]:
    c = client()
    return guarded_call(
        f"events:{sport}",
        lambda: c.get_events(sport),
        cost=1,
        essential=True,
        meta={"sport": sport},
    ) or []


def get_event_player_props(
    event_id: str,
    markets: list[str] | None = None,
    sport: str = SPORT,
) -> dict[str, Any]:
    selected = markets or PLAYER_MARKETS
    c = client()

    # One request per event. Keep market list focused so payload stays useful.
    return guarded_call(
        f"event_odds:{sport}:{event_id}",
        lambda: c.get_odds(sport, event_id=event_id, markets=selected),
        cost=1,
        essential=True,
        meta={"sport": sport, "eventId": event_id, "markets": selected},
    ) or {}


def get_bulk_game_lines(
    sport: str = SPORT,
    markets: list[str] | None = None,
    essential: bool = False,
) -> Any:
    selected = markets or GAME_MARKETS
    c = client()

    # Nonessential because OddsPapi is our primary team/game source.
    return guarded_call(
        f"game_lines:{sport}",
        lambda: c.get_odds(sport, markets=selected),
        cost=1,
        essential=essential,
        meta={"sport": sport, "markets": selected},
    )


def get_event_results(event_id: str, sport: str = SPORT, essential: bool = False) -> dict[str, Any]:
    c = client()
    return guarded_call(
        f"event_results:{sport}:{event_id}",
        lambda: c.get_event_results(sport, event_id),
        cost=1,
        essential=essential,
        meta={"sport": sport, "eventId": event_id},
    ) or {}


def get_event_ev(event_id: str, sport: str = SPORT, essential: bool = False) -> dict[str, Any]:
    c = client()
    return guarded_call(
        f"event_ev:{sport}:{event_id}",
        lambda: c.get_event_ev(sport, event_id),
        cost=1,
        essential=essential,
        meta={"sport": sport, "eventId": event_id},
    ) or {}


def get_event_stats(event_id: str, sport: str = SPORT, essential: bool = False) -> dict[str, Any]:
    c = client()

    # Depending on SDK version this may exist as get_event_stats.
    if not hasattr(c, "get_event_stats"):
        raise PropLineUnavailableError("Installed PropLine SDK does not expose get_event_stats.")

    return guarded_call(
        f"event_stats:{sport}:{event_id}",
        lambda: c.get_event_stats(sport, event_id),
        cost=1,
        essential=essential,
        meta={"sport": sport, "eventId": event_id},
    ) or {}


def value_client_status() -> dict[str, Any]:
    return {
        "sport": SPORT,
        "playerMarkets": PLAYER_MARKETS,
        "gameMarkets": GAME_MARKETS,
        "tokenGuard": guard_summary(),
    }
