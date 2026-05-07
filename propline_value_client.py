from __future__ import annotations
from local_env import load_local_env
load_local_env()

import os
from typing import Any

import requests

from propline_token_guard import can_spend, guard_summary, record_call

SPORT = "baseball_mlb"
BASE_URL = os.environ.get("PROPLINE_BASE_URL", "https://api.prop-line.com/v1").rstrip("/")
REQUEST_TIMEOUT = float(os.environ.get("PROPLINE_TIMEOUT", "20"))

PLAYER_MARKETS = [
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

GAME_MARKETS = ["h2h", "spreads", "totals"]


class PropLineBudgetError(RuntimeError):
    pass


class PropLineUnavailableError(RuntimeError):
    pass


class PropLineHttpError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"PropLine API returned {status_code}: {detail}")


def _api_key() -> str:
    api_key = os.environ.get("PROPLINE_API_KEY", "").strip()
    if not api_key:
        raise PropLineUnavailableError("Missing PROPLINE_API_KEY.")
    return api_key


def _market_param(markets: list[str] | tuple[str, ...] | str | None) -> str | None:
    if not markets:
        return None
    if isinstance(markets, str):
        return ",".join(part.strip() for part in markets.split(",") if part.strip()) or None
    return ",".join(str(market).strip() for market in markets if str(market).strip()) or None


def _error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text[:500] or response.reason or str(response.status_code)

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or payload.get("message")
        if detail:
            return str(detail)
    return str(payload)[:500]


def _request_json(path: str, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    """Call PropLine directly.

    The official SDK currently does the same join-to-comma conversion for markets,
    but using REST here avoids SDK-version drift and gives us response headers for
    quota tracking.
    """
    url = f"{BASE_URL}{path}"
    response = requests.get(
        url,
        headers={"X-API-Key": _api_key(), "Accept": "application/json"},
        params={key: value for key, value in (params or {}).items() if value not in (None, "")},
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code >= 400:
        raise PropLineHttpError(response.status_code, _error_detail(response))

    try:
        return response.json(), dict(response.headers)
    except Exception as error:
        raise PropLineUnavailableError(f"PropLine returned non-JSON response: {response.text[:200]}") from error


def guarded_request(
    label: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    cost: int = 1,
    essential: bool = True,
    meta: dict[str, Any] | None = None,
):
    if not can_spend(cost):
        if essential:
            raise PropLineBudgetError(f"PropLine token guard blocked essential call: {label}")
        raise PropLineBudgetError(f"Skipping nonessential PropLine call due to token guard: {label}")

    request_meta = {**(meta or {}), "path": path, "params": params or {}}

    try:
        result, headers = _request_json(path, params=params)
        record_call(label, cost=cost, ok=True, meta=request_meta, response_headers=headers)
        return result
    except Exception as error:
        record_call(label, cost=cost, ok=False, meta={**request_meta, "error": str(error)})
        raise


# Compatibility helper for tests/older call sites that monkeypatch or inspect the SDK client.
def client() -> Any:
    api_key = _api_key()
    try:
        from propline import PropLine
    except Exception as error:
        raise PropLineUnavailableError("Install PropLine first: python -m pip install propline") from error
    return PropLine(api_key)


def get_events(sport: str = SPORT) -> list[dict[str, Any]]:
    payload = guarded_request(
        f"events:{sport}",
        f"/sports/{sport}/events",
        cost=1,
        essential=True,
        meta={"sport": sport},
    )
    return payload if isinstance(payload, list) else []


def get_event_markets(event_id: str, sport: str = SPORT, essential: bool = False) -> list[dict[str, Any]]:
    payload = guarded_request(
        f"event_markets:{sport}:{event_id}",
        f"/sports/{sport}/events/{event_id}/markets",
        cost=1,
        essential=essential,
        meta={"sport": sport, "eventId": event_id},
    )
    return payload if isinstance(payload, list) else []


def get_event_player_props(
    event_id: str,
    markets: list[str] | None = None,
    sport: str = SPORT,
) -> dict[str, Any]:
    selected = markets or PLAYER_MARKETS
    market_param = _market_param(selected)

    # Player props are exposed only on the single-event odds endpoint.
    return guarded_request(
        f"event_odds:{sport}:{event_id}",
        f"/sports/{sport}/events/{event_id}/odds",
        params={"markets": market_param},
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
    return guarded_request(
        f"game_lines:{sport}",
        f"/sports/{sport}/odds",
        params={"markets": _market_param(selected)},
        cost=1,
        essential=essential,
        meta={"sport": sport, "markets": selected},
    )


def get_event_results(event_id: str, sport: str = SPORT, essential: bool = False, markets: list[str] | None = None) -> dict[str, Any]:
    return guarded_request(
        f"event_results:{sport}:{event_id}",
        f"/sports/{sport}/events/{event_id}/results",
        params={"markets": _market_param(markets)},
        cost=1,
        essential=essential,
        meta={"sport": sport, "eventId": event_id, "markets": markets or []},
    ) or {}


def get_event_ev(event_id: str, sport: str = SPORT, essential: bool = False, markets: list[str] | None = None) -> dict[str, Any]:
    return guarded_request(
        f"event_ev:{sport}:{event_id}",
        f"/sports/{sport}/events/{event_id}/ev",
        params={"markets": _market_param(markets)},
        cost=1,
        essential=essential,
        meta={"sport": sport, "eventId": event_id, "markets": markets or []},
    ) or {}


def get_event_stats(event_id: str, sport: str = SPORT, essential: bool = False, stat_type: list[str] | None = None) -> dict[str, Any]:
    return guarded_request(
        f"event_stats:{sport}:{event_id}",
        f"/sports/{sport}/events/{event_id}/stats",
        params={"stat_type": _market_param(stat_type)},
        cost=1,
        essential=essential,
        meta={"sport": sport, "eventId": event_id, "statType": stat_type or []},
    ) or {}


def value_client_status() -> dict[str, Any]:
    return {
        "sport": SPORT,
        "baseUrl": BASE_URL,
        "playerMarkets": PLAYER_MARKETS,
        "gameMarkets": GAME_MARKETS,
        "tokenGuard": guard_summary(),
    }
