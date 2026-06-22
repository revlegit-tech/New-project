from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import (
    get_backtest_readiness_service,
    get_blocking_work_limiter,
    get_container,
    get_ml_feature_export_service,
)
from mlb_app.api.models import (
    BacktestReadinessResponse,
    MLFeatureExportResponse,
    MLFeaturePreviewResponse,
    MLFeatureStatusResponse,
)
from mlb_app.api.routes._utils import apply_payload_status, enforce_native_mutation, with_schema_version
from mlb_app.container import AppContainer
from mlb_app.services.backtest_readiness_service import BacktestReadinessService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.ml_feature_export_service import DEFAULT_SOURCE, MLFeatureExportService

router = APIRouter(prefix="/api", tags=["ml-features"])


@router.get("/ml-features/status", response_model=MLFeatureStatusResponse, name="native_ml_features_status")
async def ml_features_status(
    service: Annotated[MLFeatureExportService, Depends(get_ml_feature_export_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    payload = await limiter.run(service.status_payload, route_name="/api/ml-features/status")
    return with_schema_version(payload, "ml-features.v1")


@router.post(
    "/admin/ml-features/export",
    response_model=MLFeatureExportResponse,
    name="native_admin_export_ml_features",
)
async def admin_export_ml_features(
    request: Request,
    response: Response,
    service: Annotated[MLFeatureExportService, Depends(get_ml_feature_export_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="data_ops", risk="high", kind="ml_feature_export")
    payload = body or {}
    result = await limiter.run(
        service.export,
        date_label=_first_query_or_body(request, payload, "date"),
        season=_optional_int(_first_query_or_body(request, payload, "season")),
        source=_first_query_or_body(request, payload, "source", DEFAULT_SOURCE),
        output_format=_first_query_or_body(request, payload, "format", "both"),
        dry_run=_boolish(_first_query_or_body(request, payload, "dryRun", _first_query_or_body(request, payload, "dry_run", "0"))),
        output_dir=_first_query_or_body(request, payload, "outputDir", _first_query_or_body(request, payload, "output_dir", "")) or None,
        timeout_seconds=180.0,
        route_name="POST /api/admin/ml-features/export",
    )
    return apply_payload_status(result, response, schema_version="ml-features.v1")


@router.get("/ml-features/preview", response_model=MLFeaturePreviewResponse, name="native_ml_features_preview")
async def ml_features_preview(
    request: Request,
    service: Annotated[MLFeatureExportService, Depends(get_ml_feature_export_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    payload = await limiter.run(
        service.preview,
        date_label=str(request.query_params.get("date") or ""),
        season=_optional_int(str(request.query_params.get("season") or "")),
        limit=_optional_int(str(request.query_params.get("limit") or "")) or 25,
        source=str(request.query_params.get("source") or DEFAULT_SOURCE),
        timeout_seconds=max(30.0, float(container.settings.playerboard_timeout_seconds)),
        route_name="/api/ml-features/preview",
    )
    return with_schema_version(payload, "ml-features.v1")


@router.get(
    "/ml-features/backtest-readiness",
    response_model=BacktestReadinessResponse,
    name="native_ml_features_backtest_readiness",
)
async def ml_features_backtest_readiness(
    request: Request,
    service: Annotated[BacktestReadinessService, Depends(get_backtest_readiness_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    payload = await limiter.run(
        service.evaluate,
        date_label=str(request.query_params.get("date") or ""),
        season=_optional_int(str(request.query_params.get("season") or "")),
        source=str(request.query_params.get("source") or DEFAULT_SOURCE),
        timeout_seconds=max(30.0, float(container.settings.playerboard_timeout_seconds)),
        route_name="/api/ml-features/backtest-readiness",
    )
    return with_schema_version(payload, "ml-features.v1")


def _first_query_or_body(request: Request, body: dict[str, Any], key: str, fallback: str = "") -> str:
    value = request.query_params.get(key)
    if value is not None:
        return str(value)
    candidate = body.get(key, fallback)
    return str(candidate if candidate is not None else fallback)


def _boolish(value: str, *, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value: str) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None
