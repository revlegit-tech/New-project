from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_blocking_work_limiter, get_model_card_service, query_params
from mlb_app.api.models import ModelCardsResponse
from mlb_app.api.routes._utils import model_cards_contract
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.model_card_service import ModelCardService

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/model-cards", response_model=ModelCardsResponse, name="native_model_cards")
async def model_cards(
    request: Request,
    service: Annotated[ModelCardService, Depends(get_model_card_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    payload = await limiter.run(service.payload, query_params(request), route_name="/api/model-cards")
    return model_cards_contract(payload, "model-cards.v1")


@router.get("/model-card", response_model=ModelCardsResponse, name="native_model_card")
async def model_card(
    request: Request,
    service: Annotated[ModelCardService, Depends(get_model_card_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    payload = await limiter.run(service.payload, query_params(request), route_name="/api/model-cards")
    return model_cards_contract(payload, "model-cards.v1")


@router.get("/model-cards/{market}", response_model=ModelCardsResponse, name="native_model_card_by_market")
async def model_card_by_market(
    market: str,
    service: Annotated[ModelCardService, Depends(get_model_card_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    payload = await limiter.run(service.payload, {"market": [market]}, route_name="/api/model-cards/{market}")
    return model_cards_contract(payload, "model-cards.v1")
