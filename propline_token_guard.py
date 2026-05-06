from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "cache" / "propline" / "token_guard_state.json"

DEFAULT_DAILY_LIMIT = int(os.environ.get("PROPLINE_DAILY_LIMIT", "1000"))
DEFAULT_RESERVED_TOKENS = int(os.environ.get("PROPLINE_RESERVED_TOKENS", "150"))


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"day": utc_day(), "estimatedUsed": 0, "calls": []}

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {"day": utc_day(), "estimatedUsed": 0, "calls": []}

    if state.get("day") != utc_day():
        return {"day": utc_day(), "estimatedUsed": 0, "calls": []}

    state.setdefault("estimatedUsed", 0)
    state.setdefault("calls", [])
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def remaining_tokens(
    daily_limit: int = DEFAULT_DAILY_LIMIT,
    reserved_tokens: int = DEFAULT_RESERVED_TOKENS,
) -> int:
    state = load_state()
    return max(0, int(daily_limit) - int(state.get("estimatedUsed", 0)) - int(reserved_tokens))


def can_spend(
    cost: int = 1,
    daily_limit: int = DEFAULT_DAILY_LIMIT,
    reserved_tokens: int = DEFAULT_RESERVED_TOKENS,
) -> bool:
    return remaining_tokens(daily_limit=daily_limit, reserved_tokens=reserved_tokens) >= int(cost)


def record_call(
    endpoint: str,
    cost: int = 1,
    ok: bool = True,
    meta: dict[str, Any] | None = None,
    response_headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_state()

    # If PropLine returns real quota headers, trust them.
    headers = response_headers or {}
    used_header = headers.get("X-Daily-Used") or headers.get("x-daily-used")
    limit_header = headers.get("X-Daily-Limit") or headers.get("x-daily-limit")

    if used_header is not None:
        try:
            state["estimatedUsed"] = int(used_header)
        except Exception:
            state["estimatedUsed"] = int(state.get("estimatedUsed", 0)) + int(cost)
    else:
        state["estimatedUsed"] = int(state.get("estimatedUsed", 0)) + int(cost)

    if limit_header is not None:
        try:
            state["dailyLimit"] = int(limit_header)
        except Exception:
            pass

    call = {
        "at": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "cost": int(cost),
        "ok": bool(ok),
        "meta": meta or {},
    }

    calls = list(state.get("calls", []))
    calls.append(call)
    state["calls"] = calls[-500:]

    save_state(state)
    return state


def guard_summary() -> dict[str, Any]:
    state = load_state()
    return {
        "day": state.get("day"),
        "estimatedUsed": int(state.get("estimatedUsed", 0)),
        "dailyLimit": int(state.get("dailyLimit", DEFAULT_DAILY_LIMIT)),
        "reservedTokens": DEFAULT_RESERVED_TOKENS,
        "remainingUsable": remaining_tokens(),
        "statePath": str(STATE_PATH),
    }
