from __future__ import annotations

from dataclasses import dataclass, field

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.inference.model_loader import ModelLoader
from mlb_app.ml.inference.prediction_service import PredictionService
from mlb_app.ml.inference.probability_blender import ProbabilityBlender
from mlb_app.repositories.bankroll_repository import BankrollRepository
from mlb_app.repositories.board_row_repository import BoardRowRepository
from mlb_app.repositories.board_snapshot_repository import BoardSnapshotRepository
from mlb_app.repositories.collector_run_repository import CollectorRunRepository
from mlb_app.repositories.data_health_repository import DataHealthRepository
from mlb_app.repositories.db import SQLiteDatabase
from mlb_app.repositories.edge_board_snapshot_repository import EdgeBoardSnapshotRepository
from mlb_app.repositories.game_environment_repository import GameEnvironmentRepository
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.picks_repository import PicksRepository
from mlb_app.repositories.player_metric_repository import PlayerMetricRepository
from mlb_app.repositories.playerboard_snapshot_repository import PlayerboardSnapshotRepository
from mlb_app.repositories.playerboard_repository import PlayerboardRepository
from mlb_app.repositories.prop_repository import PropRepository
from mlb_app.repositories.statcast_repository import StatcastRepository
from mlb_app.observability.metrics import MetricsRegistry, default_registry
from mlb_app.repositories.prediction_events_repository import PredictionEventsRepository
from mlb_app.repositories.research_report_repository import ResearchReportRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.alert_service import AlertService
from mlb_app.services.app_status_service import AppStatusService
from mlb_app.services.backtest_readiness_service import BacktestReadinessService
from mlb_app.services.backtest_dataset_builder_service import BacktestDatasetBuilderService
from mlb_app.services.bankroll_service import BankrollService
from mlb_app.services.baseball_savant_feature_service import BaseballSavantFeatureService
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.board_cache import BoardCache
from mlb_app.services.data_health_dashboard_service import DataHealthDashboardService
from mlb_app.services.data_health_service import DataHealthService
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.edge_report_service import EdgeReportService
from mlb_app.services.feature_store_service import FeatureStoreService
from mlb_app.services.game_environment_feature_service import GameEnvironmentFeatureService
from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.game_market_feature_lookup_service import GameMarketFeatureLookupService
from mlb_app.services.historical_game_odds_import_service import HistoricalGameOddsImportService
from mlb_app.services.ml_feature_export_service import MLFeatureExportService
from mlb_app.services.model_card_service import ModelCardService
from mlb_app.services.model_readiness_service import ModelReadinessService
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.mlb_market_registry_service import MLBMarketRegistryService
from mlb_app.services.model_training_service import ModelTrainingService
from mlb_app.services.picks_service import PicksService
from mlb_app.services.player_prop_label_builder_service import PlayerPropLabelBuilderService
from mlb_app.services.prediction_audit_service import PredictionAuditService
from mlb_app.services.propline_props_service import ProplinePropsService
from mlb_app.services.shadow_model_summary_service import ShadowModelSummaryService
from mlb_app.services.statcast_ingestion_service import StatcastIngestionService
from mlb_app.services.playerboard_read_service import PlayerboardReadService
from mlb_app.services.playerboard_service import PlayerboardService
from mlb_app.services.product_state_service import ProductStateService
from mlb_app.services.prop_detail_service import PropDetailService
from mlb_app.services.workflow_health_service import WorkflowHealthService
from mlb_app.security.rate_limit import TokenBucketRateLimiter


@dataclass(slots=True)
class AppContainer:
    """Application-scoped dependency container for the native FastAPI runtime.

    Sprint 4 moves route ownership into ``mlb_app.api``. The container keeps
    repositories and services as process-level dependencies instead of letting
    FastAPI handlers instantiate them per request. Tests can build an isolated
    container by passing a ``Settings`` instance pointed at a temporary root/DB.
    """

    settings: Settings = default_settings
    db: SQLiteDatabase = field(init=False)
    warehouse_db: WarehouseDatabase = field(init=False)
    board_cache: BoardCache = field(init=False)
    blocking_work_limiter: BlockingWorkLimiter = field(init=False)
    read_rate_limiter: TokenBucketRateLimiter = field(init=False)
    metrics: MetricsRegistry = field(default_factory=default_registry)

    playerboard_repository: PlayerboardRepository = field(init=False)
    board_row_repository: BoardRowRepository = field(init=False)
    board_snapshot_repository: BoardSnapshotRepository = field(init=False)
    picks_repository: PicksRepository = field(init=False)
    bankroll_repository: BankrollRepository = field(init=False)
    prediction_events_repository: PredictionEventsRepository = field(init=False)
    collector_run_repository: CollectorRunRepository = field(init=False)
    playerboard_snapshot_db_repository: PlayerboardSnapshotRepository = field(init=False)
    edge_board_snapshot_db_repository: EdgeBoardSnapshotRepository = field(init=False)
    prop_repository: PropRepository = field(init=False)
    data_health_repository: DataHealthRepository = field(init=False)
    research_report_repository: ResearchReportRepository = field(init=False)
    historical_game_odds_repository: HistoricalGameOddsRepository = field(init=False)
    statcast_repository: StatcastRepository = field(init=False)
    player_metric_repository: PlayerMetricRepository = field(init=False)
    game_environment_repository: GameEnvironmentRepository = field(init=False)

    grading_service: GradingStateService = field(init=False)
    data_health_service: DataHealthService = field(init=False)
    data_health_dashboard_service: DataHealthDashboardService = field(init=False)
    data_status_service: DataStatusService = field(init=False)
    historical_game_odds_import_service: HistoricalGameOddsImportService = field(init=False)
    game_market_feature_lookup_service: GameMarketFeatureLookupService = field(init=False)
    baseball_savant_feature_service: BaseballSavantFeatureService = field(init=False)
    game_environment_feature_service: GameEnvironmentFeatureService = field(init=False)
    statcast_ingestion_service: StatcastIngestionService = field(init=False)
    feature_store_service: FeatureStoreService = field(init=False)
    product_state_service: ProductStateService = field(init=False)
    model_registry_service: ModelRegistryService = field(init=False)
    mlb_market_registry_service: MLBMarketRegistryService = field(init=False)
    model_training_service: ModelTrainingService = field(init=False)
    model_loader: ModelLoader = field(init=False)
    probability_blender: ProbabilityBlender = field(init=False)
    prediction_service: PredictionService = field(init=False)
    model_readiness_service: ModelReadinessService = field(init=False)
    workflow_health_service: WorkflowHealthService = field(init=False)
    model_card_service: ModelCardService = field(init=False)
    shadow_model_summary_service: ShadowModelSummaryService = field(init=False)
    playerboard_read_service: PlayerboardReadService = field(init=False)
    playerboard_service: PlayerboardService = field(init=False)
    edge_board_service: EdgeBoardService = field(init=False)
    edge_report_service: EdgeReportService = field(init=False)
    ml_feature_export_service: MLFeatureExportService = field(init=False)
    player_prop_label_builder_service: PlayerPropLabelBuilderService = field(init=False)
    backtest_dataset_builder_service: BacktestDatasetBuilderService = field(init=False)
    backtest_readiness_service: BacktestReadinessService = field(init=False)
    prop_detail_service: PropDetailService = field(init=False)
    bankroll_service: BankrollService = field(init=False)
    picks_service: PicksService = field(init=False)
    prediction_audit_service: PredictionAuditService = field(init=False)
    propline_props_service: ProplinePropsService = field(init=False)
    alert_service: AlertService = field(init=False)
    app_status_service: AppStatusService = field(init=False)

    def __post_init__(self) -> None:
        self.db = SQLiteDatabase(self.settings.state_db_path)
        self.db.initialize()
        self.warehouse_db = WarehouseDatabase.from_settings(self.settings)
        self.board_cache = BoardCache(
            ttl_seconds=self.settings.board_cache_ttl_seconds,
            max_keys=self.settings.board_cache_max_keys,
            metrics=self.metrics,
        )
        self.blocking_work_limiter = BlockingWorkLimiter(
            max_concurrent=self.settings.blocking_work_max_concurrent,
            timeout_seconds=self.settings.blocking_work_timeout_seconds,
        )
        self.read_rate_limiter = TokenBucketRateLimiter(max_buckets=self.settings.rate_limit_max_buckets)

        self.playerboard_repository = PlayerboardRepository(settings=self.settings)
        self.board_row_repository = BoardRowRepository(self.settings, db=self.db)
        self.board_snapshot_repository = BoardSnapshotRepository(
            self.settings,
            db=self.db,
            row_repository=self.board_row_repository,
        )
        self.picks_repository = PicksRepository(self.settings, db=self.db)
        self.bankroll_repository = BankrollRepository(self.settings, db=self.db)
        self.prediction_events_repository = PredictionEventsRepository(self.settings, db=self.db)
        self.collector_run_repository = CollectorRunRepository(self.warehouse_db)
        self.playerboard_snapshot_db_repository = PlayerboardSnapshotRepository(
            self.warehouse_db,
            settings=self.settings,
        )
        self.edge_board_snapshot_db_repository = EdgeBoardSnapshotRepository(
            self.warehouse_db,
            settings=self.settings,
        )
        self.prop_repository = PropRepository(self.warehouse_db)
        self.data_health_repository = DataHealthRepository(self.warehouse_db)
        self.research_report_repository = ResearchReportRepository(self.warehouse_db)
        self.historical_game_odds_repository = HistoricalGameOddsRepository(
            self.warehouse_db,
            settings=self.settings,
        )
        self.statcast_repository = StatcastRepository(
            self.warehouse_db,
            settings=self.settings,
        )
        self.player_metric_repository = PlayerMetricRepository(
            self.warehouse_db,
            settings=self.settings,
        )
        self.game_environment_repository = GameEnvironmentRepository(
            self.warehouse_db,
            settings=self.settings,
        )

        self.grading_service = GradingStateService(settings=self.settings)
        self.product_state_service = ProductStateService(settings=self.settings)
        self.data_health_service = DataHealthService(
            grading_service=self.grading_service,
            product_state_service=self.product_state_service,
            settings=self.settings,
        )
        self.historical_game_odds_import_service = HistoricalGameOddsImportService(
            self.historical_game_odds_repository,
            settings=self.settings,
        )
        self.game_market_feature_lookup_service = GameMarketFeatureLookupService(
            self.historical_game_odds_repository,
            settings=self.settings,
        )
        self.baseball_savant_feature_service = BaseballSavantFeatureService(self.player_metric_repository)
        self.game_environment_feature_service = GameEnvironmentFeatureService(self.game_environment_repository)
        self.statcast_ingestion_service = StatcastIngestionService(
            statcast_repository=self.statcast_repository,
            player_metric_repository=self.player_metric_repository,
            savant_feature_service=self.baseball_savant_feature_service,
        )
        self.feature_store_service = FeatureStoreService(
            savant_feature_service=self.baseball_savant_feature_service,
            game_environment_feature_service=self.game_environment_feature_service,
        )
        self.model_registry_service = ModelRegistryService(settings=self.settings)
        self.mlb_market_registry_service = MLBMarketRegistryService(settings=self.settings)
        self.model_training_service = ModelTrainingService(settings=self.settings)
        self.model_loader = ModelLoader(
            settings=self.settings,
            registry_service=self.model_registry_service,
        )
        self.probability_blender = ProbabilityBlender()
        self.prediction_service = PredictionService(
            settings=self.settings,
            model_loader=self.model_loader,
            probability_blender=self.probability_blender,
        )
        self.model_readiness_service = ModelReadinessService(self.model_registry_service)
        self.workflow_health_service = WorkflowHealthService(settings=self.settings)
        self.prediction_audit_service = PredictionAuditService(
            self.settings,
            repository=self.prediction_events_repository,
            model_registry_service=self.model_registry_service,
        )
        self.propline_props_service = ProplinePropsService()
        self.alert_service = AlertService(metrics=self.metrics)
        self.model_card_service = ModelCardService(
            self.settings,
            grading_service=self.grading_service,
            readiness_service=self.model_readiness_service,
            registry_service=self.model_registry_service,
        )
        self.shadow_model_summary_service = ShadowModelSummaryService(
            self.settings,
            registry_service=self.model_registry_service,
        )
        self.playerboard_read_service = PlayerboardReadService(
            repository=self.playerboard_repository,
            snapshot_repository=self.board_snapshot_repository,
            db_snapshot_repository=self.playerboard_snapshot_db_repository,
            grading_service=self.grading_service,
            readiness_service=self.model_readiness_service,
            product_state_service=self.product_state_service,
            game_market_feature_lookup_service=self.game_market_feature_lookup_service,
            settings=self.settings,
            metrics=self.metrics,
        )
        self.data_status_service = DataStatusService(
            settings=self.settings,
            data_health_repository=self.data_health_repository,
            historical_game_odds_repository=self.historical_game_odds_repository,
            game_market_feature_lookup_service=self.game_market_feature_lookup_service,
            playerboard_read_service=self.playerboard_read_service,
        )
        self.playerboard_service = PlayerboardService(
            repository=self.playerboard_repository,
            grading_service=self.grading_service,
            readiness_service=self.model_readiness_service,
            product_state_service=self.product_state_service,
            read_service=self.playerboard_read_service,
            game_market_feature_lookup_service=self.game_market_feature_lookup_service,
            market_registry_service=self.mlb_market_registry_service,
            settings=self.settings,
        )
        self.bankroll_service = BankrollService(
            self.settings,
            repository=self.bankroll_repository,
        )
        self.picks_service = PicksService(
            self.settings,
            repository=self.picks_repository,
            bankroll_service=self.bankroll_service,
        )
        self.edge_board_service = EdgeBoardService(
            playerboard_service=self.playerboard_service,
            model_card_service=self.model_card_service,
            snapshot_repository=self.edge_board_snapshot_db_repository,
            board_cache=self.board_cache,
            game_market_feature_lookup_service=self.game_market_feature_lookup_service,
            metrics=self.metrics,
            market_registry_service=self.mlb_market_registry_service,
            settings=self.settings,
        )
        self.edge_report_service = EdgeReportService(
            edge_board_service=self.edge_board_service,
            report_repository=self.research_report_repository,
        )
        self.ml_feature_export_service = MLFeatureExportService(
            settings=self.settings,
            playerboard_service=self.playerboard_service,
            edge_board_service=self.edge_board_service,
            game_market_feature_lookup_service=self.game_market_feature_lookup_service,
        )
        self.player_prop_label_builder_service = PlayerPropLabelBuilderService(
            settings=self.settings,
            feature_export_service=self.ml_feature_export_service,
        )
        self.backtest_dataset_builder_service = BacktestDatasetBuilderService(
            settings=self.settings,
            feature_export_service=self.ml_feature_export_service,
            label_builder_service=self.player_prop_label_builder_service,
        )
        self.backtest_readiness_service = BacktestReadinessService(
            feature_export_service=self.ml_feature_export_service,
            training_builder_service=self.backtest_dataset_builder_service,
        )
        self.data_health_dashboard_service = DataHealthDashboardService(
            data_health_service=self.data_health_service,
            playerboard_service=self.playerboard_service,
            grading_service=self.grading_service,
            workflow_service=self.workflow_health_service,
            product_state_service=self.product_state_service,
            model_registry_service=self.model_registry_service,
            settings=self.settings,
        )
        self.prop_detail_service = PropDetailService(
            read_service=self.playerboard_read_service,
            model_card_service=self.model_card_service,
            picks_service=self.picks_service,
        )
        self.app_status_service = AppStatusService(
            playerboard_service=self.playerboard_service,
            grading_service=self.grading_service,
            model_registry_service=self.model_registry_service,
            workflow_service=self.workflow_health_service,
            product_state_service=self.product_state_service,
            alert_service=self.alert_service,
            board_cache=self.board_cache,
            settings=self.settings,
        )


def build_container(runtime_settings: Settings | None = None) -> AppContainer:
    return AppContainer(settings=runtime_settings or default_settings)
