from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.playerboard_service import PlayerboardService


def playerboard_health(context: RequestContext) -> dict[str, Any]:
    return PlayerboardService().health_payload(context.query)


def playerboard(context: RequestContext) -> dict[str, Any]:
    return PlayerboardService().board_payload(context.query)
