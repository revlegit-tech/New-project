from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import get_bankroll_service, get_blocking_work_limiter, get_picks_service, query_params
from mlb_app.api.models import BankrollSettingsResponse, ExposureSummaryResponse, PickResponse
from mlb_app.api.routes._utils import apply_payload_status, enforce_native_mutation, exposure_contract, picks_contract, with_schema_version
from mlb_app.services.bankroll_service import BankrollService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.picks_service import PicksService

router = APIRouter(prefix="/api", tags=["picks"])


@router.get("/my-picks", response_model=PickResponse, name="native_my_picks")
async def my_picks(
    request: Request,
    service: Annotated[PicksService, Depends(get_picks_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    payload = await limiter.run(service.payload, query_params(request), route_name="/api/my-picks")
    return picks_contract(payload, "picks.v1")


@router.post("/my-picks", response_model=PickResponse, name="native_create_pick")
async def create_pick(
    request: Request,
    response: Response,
    body: dict[str, Any],
    service: Annotated[PicksService, Depends(get_picks_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    enforce_native_mutation(request, owner="bettor_state", risk="medium", kind="pick_write")
    payload = await limiter.run(service.create, body, route_name="POST /api/my-picks")
    return apply_payload_status(picks_contract(payload, "picks.v1"), response)


@router.post("/my-picks/update", response_model=PickResponse, name="native_update_pick")
async def update_pick(
    request: Request,
    response: Response,
    body: dict[str, Any],
    service: Annotated[PicksService, Depends(get_picks_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    enforce_native_mutation(request, owner="bettor_state", risk="medium", kind="pick_write")
    payload = await limiter.run(service.update, body, route_name="POST /api/my-picks/update")
    return apply_payload_status(picks_contract(payload, "picks.v1"), response)


@router.get("/exposure/summary", response_model=ExposureSummaryResponse, name="native_exposure_summary")
async def exposure_summary(
    service: Annotated[PicksService, Depends(get_picks_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    def _payload() -> dict[str, Any]:
        return {
            "status": "ok",
            "settings": service.bankroll_service.get_settings().to_api(),
            "exposure": service.exposure(),
        }

    payload = await limiter.run(_payload, route_name="/api/exposure/summary")
    return exposure_contract(payload, "exposure.v1")


@router.get("/bankroll/settings", response_model=BankrollSettingsResponse, name="native_bankroll_settings")
async def bankroll_settings(
    service: Annotated[BankrollService, Depends(get_bankroll_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    payload = await limiter.run(service.payload, route_name="/api/bankroll/settings")
    return with_schema_version(payload, "bankroll-settings.v1")


@router.post("/bankroll/settings", response_model=BankrollSettingsResponse, name="native_update_bankroll_settings")
async def update_bankroll_settings(
    request: Request,
    response: Response,
    body: dict[str, Any],
    service: Annotated[BankrollService, Depends(get_bankroll_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    enforce_native_mutation(request, owner="risk_controls", risk="high", kind="bankroll_write")
    payload = await limiter.run(service.update, body, route_name="POST /api/bankroll/settings")
    return apply_payload_status(with_schema_version(payload, "bankroll-settings.v1"), response)
