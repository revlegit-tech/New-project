from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.bankroll_service import BankrollService
from mlb_app.services.picks_service import PicksService


def my_picks(context: RequestContext) -> dict[str, Any]:
    return PicksService().payload(context.query)


def create_pick(context: RequestContext) -> dict[str, Any]:
    return PicksService().create(context.body)


def update_pick(context: RequestContext) -> dict[str, Any]:
    return PicksService().update(context.body)


def bankroll_settings(context: RequestContext) -> dict[str, Any]:
    return BankrollService().payload()


def update_bankroll_settings(context: RequestContext) -> dict[str, Any]:
    return BankrollService().update(context.body)


def exposure_summary(context: RequestContext) -> dict[str, Any]:
    service = PicksService()
    return {"status": "ok", "settings": service.bankroll_service.get_settings().to_api(), "exposure": service.exposure()}
