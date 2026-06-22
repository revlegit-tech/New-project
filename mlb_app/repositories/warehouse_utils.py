from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value: Any) -> str:
    return str(value or "").strip()


def json_text(value: Any, default: Any = None) -> str:
    payload = default if value is None else value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(clean(part).encode("utf-8"))
        digest.update(b"|")
    return f"{prefix}_{digest.hexdigest()[:24]}"


def first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


def date_from_row(row: Mapping[str, Any], fallback: str = "") -> str:
    return clean(first(row, "date", "game_date", "gameDate", "slateDate")) or fallback


def market_from_row(row: Mapping[str, Any]) -> str:
    return clean(first(row, "market", "market_key", "marketKey", "baseMarket"))
