from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from mlb_app.api.dependencies import get_blocking_work_limiter, get_container
from mlb_app.api.models import (
    BaselineModelStatusResponse,
    CollectorCheckResponse,
    DataSourceCapabilityResponse,
    FeatureStoreMaterializerResponse,
    ModelBacktestStatusResponse,
    ModelCalibrationStatusResponse,
    ModelTrainingReadinessResponse,
)
from mlb_app.container import AppContainer
from mlb_app.services.baseline_model_training_service import BaselineModelTrainingService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.collector_verification_service import CollectorVerificationService
from mlb_app.services.data_source_capability_service import DataSourceCapabilityService
from mlb_app.services.data_freshness_service import DataFreshnessService
from mlb_app.services.feature_store_materializer import FeatureStoreMaterializer
from mlb_app.services.model_backtest_service import ModelBacktestService
from mlb_app.services.model_calibration_service import ModelCalibrationService
from mlb_app.services.model_training_readiness_service import ModelTrainingReadinessService
from mlb_app.services.runtime_status_service import RuntimeStatusService

router = APIRouter(prefix="/api", tags=["runtime"])


@router.get("/runtime/status", name="native_runtime_status")
async def runtime_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    service = RuntimeStatusService(container.settings)
    return await limiter.run(service.runtime_status, route_name="/api/runtime/status")


@router.get("/runtime/collector-check", response_model=CollectorCheckResponse, name="native_runtime_collector_check")
async def collector_check(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
) -> dict:
    service = CollectorVerificationService(
        settings=container.settings,
        board_snapshot_repository=container.board_snapshot_repository,
        edge_board_service=container.edge_board_service,
        runtime_status_service=RuntimeStatusService(container.settings),
    )
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.payload,
        date_label=date,
        season=selected_season,
        route_name="/api/runtime/collector-check",
    )


@router.get(
    "/runtime/data-source-capabilities",
    response_model=DataSourceCapabilityResponse,
    name="native_runtime_data_source_capabilities",
)
async def data_source_capabilities(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
) -> dict:
    service = DataSourceCapabilityService(container.settings)
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.payload,
        date_label=date,
        season=selected_season,
        route_name="/api/runtime/data-source-capabilities",
    )


@router.get(
    "/runtime/feature-store/status",
    response_model=FeatureStoreMaterializerResponse,
    name="native_runtime_feature_store_status",
)
async def feature_store_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
    materialize: Annotated[bool, Query()] = False,
) -> dict:
    service = FeatureStoreMaterializer(container.settings)
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.status,
        date_label=date,
        season=selected_season,
        materialize=materialize,
        route_name="/api/runtime/feature-store/status",
    )


@router.get(
    "/runtime/model-training/readiness",
    response_model=ModelTrainingReadinessResponse,
    name="native_runtime_model_training_readiness",
)
async def model_training_readiness(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
    market: Annotated[str | None, Query()] = None,
) -> dict:
    service = ModelTrainingReadinessService(container.settings)
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.payload,
        date_label=date,
        season=selected_season,
        market=market,
        route_name="/api/runtime/model-training/readiness",
    )


@router.get(
    "/runtime/baseline-model/status",
    response_model=BaselineModelStatusResponse,
    name="native_runtime_baseline_model_status",
)
async def baseline_model_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
    market: Annotated[str, Query()] = "batter_hits",
) -> dict:
    service = BaselineModelTrainingService(container.settings)
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.status,
        date_label=date,
        season=selected_season,
        market=market,
        route_name="/api/runtime/baseline-model/status",
    )


@router.get(
    "/runtime/model-calibration/status",
    response_model=ModelCalibrationStatusResponse,
    name="native_runtime_model_calibration_status",
)
async def model_calibration_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
    market: Annotated[str, Query()] = "batter_hits",
) -> dict:
    service = ModelCalibrationService(container.settings)
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.status,
        date_label=date,
        season=selected_season,
        market=market,
        route_name="/api/runtime/model-calibration/status",
    )


@router.get(
    "/runtime/model-backtest/status",
    response_model=ModelBacktestStatusResponse,
    name="native_runtime_model_backtest_status",
)
async def model_backtest_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
    season: Annotated[int | None, Query()] = None,
    market: Annotated[str, Query()] = "batter_hits",
) -> dict:
    service = ModelBacktestService(container.settings)
    selected_season = season if season is not None else container.settings.current_season
    return await limiter.run(
        service.status,
        date_label=date,
        season=selected_season,
        market=market,
        route_name="/api/runtime/model-backtest/status",
    )


@router.get("/workflow/status", name="native_workflow_status")
async def workflow_status(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict:
    service = RuntimeStatusService(container.settings)
    return await limiter.run(service.workflow_status, route_name="/api/workflow/status")


@router.get("/data-freshness", name="native_data_freshness")
async def data_freshness(
    container: Annotated[AppContainer, Depends(get_container)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    date: Annotated[str | None, Query()] = None,
) -> dict:
    service = DataFreshnessService(container.settings)
    return await limiter.run(service.payload, date, route_name="/api/data-freshness")
