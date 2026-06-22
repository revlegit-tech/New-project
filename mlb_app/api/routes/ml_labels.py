from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import (
    get_backtest_dataset_builder_service,
    get_blocking_work_limiter,
    get_container,
    get_player_prop_label_builder_service,
)
from mlb_app.api.models import (
    MLLabelStatusResponse,
    PlayerPropLabelBuildResponse,
    PlayerPropLabelPreviewResponse,
    PlayerPropTrainingBuildResponse,
    PlayerPropTrainingPreviewResponse,
)
from mlb_app.api.routes._utils import apply_payload_status, enforce_native_mutation, with_schema_version
from mlb_app.container import AppContainer
from mlb_app.services.backtest_dataset_builder_service import BacktestDatasetBuilderService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.ml_feature_export_service import DEFAULT_SOURCE
from mlb_app.services.player_prop_label_builder_service import LABEL_API_SCHEMA_VERSION, PlayerPropLabelBuilderService

router = APIRouter(prefix="/api", tags=["ml-labels"])


@router.get("/ml-labels/status", response_model=MLLabelStatusResponse, name="native_ml_labels_status")
async def ml_labels_status(
    service: Annotated[PlayerPropLabelBuilderService, Depends(get_player_prop_label_builder_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    payload = await limiter.run(service.status_payload, route_name="/api/ml-labels/status")
    return with_schema_version(payload, LABEL_API_SCHEMA_VERSION)


@router.post(
    "/admin/ml-labels/build",
    response_model=PlayerPropLabelBuildResponse,
    name="native_admin_build_ml_labels",
)
async def admin_build_ml_labels(
    request: Request,
    response: Response,
    service: Annotated[PlayerPropLabelBuilderService, Depends(get_player_prop_label_builder_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="data_ops", risk="high", kind="ml_label_build")
    payload = body or {}
    result = await limiter.run(
        service.build_labels,
        date_label=_first_query_or_body(request, payload, "date"),
        season=_optional_int(_first_query_or_body(request, payload, "season")),
        source=_first_query_or_body(request, payload, "source", DEFAULT_SOURCE),
        dry_run=_boolish(_first_query_or_body(request, payload, "dryRun", _first_query_or_body(request, payload, "dry_run", "0"))),
        include_ungraded=_boolish(
            _first_query_or_body(request, payload, "includeUngraded", _first_query_or_body(request, payload, "include_ungraded", "0"))
        ),
        output_format=_first_query_or_body(request, payload, "format", "both"),
        output_dir=_first_query_or_body(request, payload, "outputDir", _first_query_or_body(request, payload, "output_dir", "")) or None,
        timeout_seconds=180.0,
        route_name="POST /api/admin/ml-labels/build",
    )
    return apply_payload_status(result, response, schema_version=LABEL_API_SCHEMA_VERSION)


@router.post(
    "/admin/ml-training/build",
    response_model=PlayerPropTrainingBuildResponse,
    name="native_admin_build_ml_training",
)
async def admin_build_ml_training(
    request: Request,
    response: Response,
    service: Annotated[BacktestDatasetBuilderService, Depends(get_backtest_dataset_builder_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="data_ops", risk="high", kind="ml_training_build")
    payload = body or {}
    result = await limiter.run(
        service.build_training_dataset,
        date_label=_first_query_or_body(request, payload, "date"),
        season=_optional_int(_first_query_or_body(request, payload, "season")),
        source=_first_query_or_body(request, payload, "source", DEFAULT_SOURCE),
        dry_run=_boolish(_first_query_or_body(request, payload, "dryRun", _first_query_or_body(request, payload, "dry_run", "0"))),
        include_ungraded=_boolish(
            _first_query_or_body(request, payload, "includeUngraded", _first_query_or_body(request, payload, "include_ungraded", "0"))
        ),
        output_format=_first_query_or_body(request, payload, "format", "both"),
        output_dir=_first_query_or_body(request, payload, "outputDir", _first_query_or_body(request, payload, "output_dir", "")) or None,
        timeout_seconds=180.0,
        route_name="POST /api/admin/ml-training/build",
    )
    return apply_payload_status(result, response, schema_version="ml-training.v1")


@router.get("/ml-labels/preview", response_model=PlayerPropLabelPreviewResponse, name="native_ml_labels_preview")
async def ml_labels_preview(
    request: Request,
    service: Annotated[PlayerPropLabelBuilderService, Depends(get_player_prop_label_builder_service)],
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
        route_name="/api/ml-labels/preview",
    )
    return with_schema_version(payload, LABEL_API_SCHEMA_VERSION)


@router.get("/ml-training/preview", response_model=PlayerPropTrainingPreviewResponse, name="native_ml_training_preview")
async def ml_training_preview(
    request: Request,
    service: Annotated[BacktestDatasetBuilderService, Depends(get_backtest_dataset_builder_service)],
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
        route_name="/api/ml-training/preview",
    )
    return with_schema_version(payload, "ml-training.v1")


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
