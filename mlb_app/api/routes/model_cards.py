from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mlb_app.api.dependencies import get_model_card_service, query_params
from mlb_app.api.models import ModelCardsResponse
from mlb_app.services.model_card_service import ModelCardService

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/model-cards", response_model=ModelCardsResponse, name="native_model_cards")
async def model_cards(
    request: Request,
    service: Annotated[ModelCardService, Depends(get_model_card_service)],
) -> dict:
    return await asyncio.to_thread(service.payload, query_params(request))


@router.get("/model-card", response_model=ModelCardsResponse, name="native_model_card")
async def model_card(
    request: Request,
    service: Annotated[ModelCardService, Depends(get_model_card_service)],
) -> dict:
    return await asyncio.to_thread(service.payload, query_params(request))


@router.get("/model-cards/{market}", response_model=ModelCardsResponse, name="native_model_card_by_market")
async def model_card_by_market(
    market: str,
    service: Annotated[ModelCardService, Depends(get_model_card_service)],
) -> dict:
    return await asyncio.to_thread(service.payload, {"market": [market]})
