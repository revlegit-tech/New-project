from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.model_card_service import ModelCardService


def model_cards(context: RequestContext) -> dict[str, Any]:
    return ModelCardService().payload(context.query)


def model_card(context: RequestContext) -> dict[str, Any]:
    payload = ModelCardService().payload(context.query)
    cards = payload.get("markets") or []
    return {
        "status": payload.get("status", "ok"),
        "version": payload.get("version"),
        "modelCard": cards[0] if cards else None,
        "policy": payload.get("policy", {}),
    }
