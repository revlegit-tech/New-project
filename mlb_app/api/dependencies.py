from __future__ import annotations

from collections import defaultdict
from typing import Annotated

from fastapi import Depends, Request

from mlb_app.container import AppContainer
from mlb_app.middleware import normalize_request_id
from mlb_app.services.app_status_service import AppStatusService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.bankroll_service import BankrollService
from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.edge_report_service import EdgeReportService
from mlb_app.services.data_health_dashboard_service import DataHealthDashboardService
from mlb_app.services.data_health_service import DataHealthService
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.backtest_readiness_service import BacktestReadinessService
from mlb_app.services.backtest_dataset_builder_service import BacktestDatasetBuilderService
from mlb_app.services.historical_game_odds_import_service import HistoricalGameOddsImportService
from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.ml_feature_export_service import MLFeatureExportService
from mlb_app.services.player_prop_label_builder_service import PlayerPropLabelBuilderService
from mlb_app.services.workflow_health_service import WorkflowHealthService
from mlb_app.observability.metrics import MetricsRegistry
from mlb_app.services.alert_service import AlertService
from mlb_app.services.model_card_service import ModelCardService
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.prediction_audit_service import PredictionAuditService
from mlb_app.services.propline_props_service import ProplinePropsService
from mlb_app.services.picks_service import PicksService
from mlb_app.services.playerboard_service import PlayerboardService
from mlb_app.services.prop_detail_service import PropDetailService
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository


def query_params(request: Request) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    for key, value in request.query_params.multi_items():
        values[str(key)].append(str(value))
    return dict(values)


def request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return normalize_request_id(rid or request.headers.get("x-request-id"))


def get_container(request: Request) -> AppContainer:
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, AppContainer):
        raise RuntimeError("FastAPI AppContainer is not configured")
    return container


def get_app_status_service(container: Annotated[AppContainer, Depends(get_container)]) -> AppStatusService:
    return container.app_status_service


def get_edge_board_service(container: Annotated[AppContainer, Depends(get_container)]) -> EdgeBoardService:
    return container.edge_board_service


def get_research_report_service(container: Annotated[AppContainer, Depends(get_container)]) -> EdgeReportService:
    return container.edge_report_service


def get_playerboard_service(container: Annotated[AppContainer, Depends(get_container)]) -> PlayerboardService:
    return container.playerboard_service


def get_prop_detail_service(container: Annotated[AppContainer, Depends(get_container)]) -> PropDetailService:
    return container.prop_detail_service


def get_model_card_service(container: Annotated[AppContainer, Depends(get_container)]) -> ModelCardService:
    return container.model_card_service


def get_picks_service(container: Annotated[AppContainer, Depends(get_container)]) -> PicksService:
    return container.picks_service


def get_bankroll_service(container: Annotated[AppContainer, Depends(get_container)]) -> BankrollService:
    return container.bankroll_service



def get_data_health_service(container: Annotated[AppContainer, Depends(get_container)]) -> DataHealthService:
    return container.data_health_service


def get_data_health_dashboard_service(container: Annotated[AppContainer, Depends(get_container)]) -> DataHealthDashboardService:
    return container.data_health_dashboard_service


def get_data_status_service(container: Annotated[AppContainer, Depends(get_container)]) -> DataStatusService:
    return container.data_status_service


def get_ml_feature_export_service(container: Annotated[AppContainer, Depends(get_container)]) -> MLFeatureExportService:
    return container.ml_feature_export_service


def get_backtest_readiness_service(container: Annotated[AppContainer, Depends(get_container)]) -> BacktestReadinessService:
    return container.backtest_readiness_service


def get_player_prop_label_builder_service(container: Annotated[AppContainer, Depends(get_container)]) -> PlayerPropLabelBuilderService:
    return container.player_prop_label_builder_service


def get_backtest_dataset_builder_service(container: Annotated[AppContainer, Depends(get_container)]) -> BacktestDatasetBuilderService:
    return container.backtest_dataset_builder_service


def get_historical_game_odds_repository(container: Annotated[AppContainer, Depends(get_container)]) -> HistoricalGameOddsRepository:
    return container.historical_game_odds_repository


def get_historical_game_odds_import_service(container: Annotated[AppContainer, Depends(get_container)]) -> HistoricalGameOddsImportService:
    return container.historical_game_odds_import_service


def get_grading_service(container: Annotated[AppContainer, Depends(get_container)]) -> GradingStateService:
    return container.grading_service


def get_workflow_health_service(container: Annotated[AppContainer, Depends(get_container)]) -> WorkflowHealthService:
    return container.workflow_health_service


def get_model_registry_service(container: Annotated[AppContainer, Depends(get_container)]) -> ModelRegistryService:
    return container.model_registry_service


def get_prediction_audit_service(container: Annotated[AppContainer, Depends(get_container)]) -> PredictionAuditService:
    return container.prediction_audit_service


def get_metrics_registry(container: Annotated[AppContainer, Depends(get_container)]) -> MetricsRegistry:
    return container.metrics


def get_alert_service(container: Annotated[AppContainer, Depends(get_container)]) -> AlertService:
    return container.alert_service


def get_propline_props_service(container: Annotated[AppContainer, Depends(get_container)]) -> ProplinePropsService:
    return container.propline_props_service


def get_blocking_work_limiter(container: Annotated[AppContainer, Depends(get_container)]) -> BlockingWorkLimiter:
    return container.blocking_work_limiter
