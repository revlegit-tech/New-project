from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.propline_props_service import PROPLINE_MARKETS, PropLineSyncRequest, sync_propline_props


def sync_props(context: RequestContext) -> dict[str, Any]:
    date_label = str((context.query.get("date") or [context.body.get("date", "")])[0] or context.body.get("date", ""))
    sport = str((context.query.get("sport") or [context.body.get("sport", "baseball_mlb")])[0] or "baseball_mlb")
    raw_markets = str((context.query.get("markets") or [context.body.get("markets", "")])[0] or "")
    if isinstance(context.body.get("markets"), list):
        markets = tuple(str(item).strip() for item in context.body.get("markets", []) if str(item).strip())
    else:
        markets = tuple(part.strip() for part in raw_markets.split(",") if part.strip()) or tuple(PROPLINE_MARKETS)
    save = str((context.query.get("save") or [context.body.get("save", "1")])[0]).lower() not in {"0", "false", "no"}
    snapshot = str((context.query.get("snapshot") or [context.body.get("snapshot", "1")])[0]).lower() not in {"0", "false", "no"}
    return sync_propline_props(PropLineSyncRequest(date=date_label, sport=sport, markets=markets, save=save, snapshot=snapshot))
