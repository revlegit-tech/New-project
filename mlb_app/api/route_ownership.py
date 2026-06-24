from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RouteOwnership:
    method: str
    path: str
    owner: str
    native_route_name: str
    legacy_handler: str
    legacy_action: str
    notes: str = ""


ROUTE_OWNERSHIP: tuple[RouteOwnership, ...] = (
    RouteOwnership("GET", "/api/app/status", "FastAPI", "native_app_status", "mlb_app.routes.health.app_status", "delete_after_parity", "Canonical product status endpoint."),
    RouteOwnership("GET", "/api/edge-board", "FastAPI", "native_edge_board", "mlb_app.routes.edge_board.edge_board", "delete", "High-traffic board endpoint; no legacy fallback."),
    RouteOwnership("GET", "/api/research/report", "FastAPI", "native_research_report", "none", "no_legacy_handler", "Daily productized MLB research report generated from EdgeBoard rows."),
    RouteOwnership("GET", "/api/playerboard", "FastAPI", "native_playerboard", "mlb_app.routes.playerboard.playerboard", "delete_after_contract_parity", "Board payload must flow through AppContainer.playerboard_service."),
    RouteOwnership("GET", "/api/playerboard/health", "FastAPI", "native_playerboard_health", "mlb_app.routes.playerboard.playerboard_health", "delete_after_health_parity", "Health contract derives from native PlayerboardService."),
    RouteOwnership("GET", "/api/prop-detail", "FastAPI", "native_prop_detail", "mlb_app.routes.prop_detail.prop_detail", "delete_after_targeted_lookup", "Detail endpoint is native-owned; indexed lookup follows in snapshot sprint."),
    RouteOwnership("GET", "/api/model-cards", "FastAPI", "native_model_cards", "mlb_app.routes.model_cards.model_cards", "delete_after_cache_hardening", "Model room list endpoint."),
    RouteOwnership("GET", "/api/model-card", "FastAPI", "native_model_card", "mlb_app.routes.model_cards.model_card", "delete_after_cache_hardening", "Single model-card query endpoint."),
    RouteOwnership("GET", "/api/model-cards/{market}", "FastAPI", "native_model_card_by_market", "mlb_app.routes.model_cards.model_card", "delete_after_cache_hardening", "Parameterized model-card detail endpoint."),
    RouteOwnership("GET", "/api/my-picks", "FastAPI", "native_my_picks", "mlb_app.routes.my_picks.my_picks", "delete_after_mutation_parity", "Tracked picks read endpoint."),
    RouteOwnership("POST", "/api/my-picks", "FastAPI", "native_create_pick", "mlb_app.routes.my_picks.create_pick", "delete_after_mutation_parity", "Mutation security enforced in native route."),
    RouteOwnership("POST", "/api/my-picks/update", "FastAPI", "native_update_pick", "mlb_app.routes.my_picks.update_pick", "delete_after_mutation_parity", "Mutation security enforced in native route."),
    RouteOwnership("GET", "/api/bankroll/settings", "FastAPI", "native_bankroll_settings", "mlb_app.routes.my_picks.bankroll_settings", "delete_after_mutation_parity", "Risk settings read endpoint."),
    RouteOwnership("POST", "/api/bankroll/settings", "FastAPI", "native_update_bankroll_settings", "mlb_app.routes.my_picks.update_bankroll_settings", "delete_after_mutation_parity", "Risk settings write endpoint."),
    RouteOwnership("GET", "/api/exposure/summary", "FastAPI", "native_exposure_summary", "mlb_app.routes.my_picks.exposure_summary", "delete_after_parity", "Exposure read endpoint."),
    RouteOwnership("POST", "/api/admin/propline/props/sync", "FastAPI", "native_admin_sync_propline_props", "mlb_app.routes.propline.sync_props", "delete", "Admin-only paid API sync; no generic legacy fallback."),
    RouteOwnership("POST", "/api/admin/historical-game-odds/import", "FastAPI", "native_admin_import_historical_game_odds", "none", "no_legacy_handler", "Historical game-market odds warehouse import; native mutation security."),
    RouteOwnership("GET", "/api/game-odds/status", "FastAPI", "native_game_odds_status", "none", "no_legacy_handler", "Historical game-market odds warehouse status."),
    RouteOwnership("GET", "/api/game-odds/lines", "FastAPI", "native_game_odds_lines", "none", "no_legacy_handler", "Historical game-market odds line rows by date."),
    RouteOwnership("GET", "/api/game-odds/features", "FastAPI", "native_game_odds_features", "none", "no_legacy_handler", "Leakage-protected historical game-market feature rows by date."),
    RouteOwnership("GET", "/api/game-odds/grades", "FastAPI", "native_game_odds_grades", "none", "no_legacy_handler", "Historical game-market grade rows by date."),
    RouteOwnership("GET", "/api/ml-features/status", "FastAPI", "native_ml_features_status", "none", "no_legacy_handler", "Safe ML feature export status."),
    RouteOwnership("GET", "/api/ml-features/preview", "FastAPI", "native_ml_features_preview", "none", "no_legacy_handler", "Safe ML feature export preview."),
    RouteOwnership("GET", "/api/ml-features/backtest-readiness", "FastAPI", "native_ml_features_backtest_readiness", "none", "no_legacy_handler", "Market-level backtest readiness summary."),
    RouteOwnership("POST", "/api/admin/ml-features/export", "FastAPI", "native_admin_export_ml_features", "none", "no_legacy_handler", "Admin-only safe ML feature export generation."),
    RouteOwnership("GET", "/api/ml-labels/status", "FastAPI", "native_ml_labels_status", "none", "no_legacy_handler", "Safe player-prop label and training dataset status."),
    RouteOwnership("GET", "/api/ml-labels/preview", "FastAPI", "native_ml_labels_preview", "none", "no_legacy_handler", "Player-prop label preview endpoint."),
    RouteOwnership("GET", "/api/ml-training/preview", "FastAPI", "native_ml_training_preview", "none", "no_legacy_handler", "Feature-label joined training preview endpoint."),
    RouteOwnership("POST", "/api/admin/ml-labels/build", "FastAPI", "native_admin_build_ml_labels", "none", "no_legacy_handler", "Admin-only player-prop label artifact builder."),
    RouteOwnership("POST", "/api/admin/ml-training/build", "FastAPI", "native_admin_build_ml_training", "none", "no_legacy_handler", "Admin-only player-prop training dataset builder."),
    RouteOwnership("GET", "/api/ml-models/status", "FastAPI", "native_ml_models_status", "none", "no_legacy_handler", "Safe ML model status endpoint."),
    RouteOwnership("GET", "/api/ml-models/registry", "FastAPI", "native_ml_models_registry", "none", "no_legacy_handler", "Safe ML model registry listing without local paths."),
    RouteOwnership("GET", "/api/ml-models/metrics", "FastAPI", "native_ml_models_metrics", "none", "no_legacy_handler", "Safe ML model metrics listing."),
    RouteOwnership("GET", "/api/ml-models/feature-coverage", "FastAPI", "native_ml_models_feature_coverage", "none", "no_legacy_handler", "Safe ML model feature coverage endpoint."),
    RouteOwnership("GET", "/api/ml-models/predictions/preview", "FastAPI", "native_ml_models_predictions_preview", "none", "no_legacy_handler", "Shadow-safe model prediction preview endpoint."),
    RouteOwnership("POST", "/api/admin/ml-models/train", "FastAPI", "native_admin_ml_models_train", "none", "no_legacy_handler", "Admin-only ML training runner wrapper."),
    RouteOwnership("POST", "/api/admin/ml-models/evaluate", "FastAPI", "native_admin_ml_models_evaluate", "none", "no_legacy_handler", "Admin-only model gate evaluation wrapper."),
    RouteOwnership("POST", "/api/admin/ml-models/promote", "FastAPI", "native_admin_ml_models_promote", "none", "no_legacy_handler", "Admin-only gated model promotion endpoint."),
    RouteOwnership("GET", "/api/actionnetwork/snapshot-health", "FastAPI", "native_actionnetwork_snapshot_health", "none", "no_legacy_handler", "ActionNetwork live-forward snapshot freshness trust endpoint."),
    RouteOwnership("GET", "/api/actionnetwork/label-eligibility", "FastAPI", "native_actionnetwork_label_eligibility", "none", "no_legacy_handler", "ActionNetwork event-confirmed label eligibility trust endpoint."),
    RouteOwnership("GET", "/api/actionnetwork/trust", "FastAPI", "native_actionnetwork_trust", "none", "no_legacy_handler", "Combined ActionNetwork snapshot and label trust endpoint."),
    RouteOwnership("GET", "/api/prediction-events", "FastAPI", "native_prediction_events", "none", "no_legacy_handler", "Prediction audit event stream; native AppContainer service only."),
    RouteOwnership("POST", "/api/prediction-events", "FastAPI", "native_record_prediction_event", "none", "no_legacy_handler", "Prediction audit write; native mutation security."),
    RouteOwnership("GET", "/api/observability/metrics", "FastAPI", "native_observability_metrics", "none", "no_legacy_handler", "Native metrics surface."),
    RouteOwnership("GET", "/api/observability/alerts", "FastAPI", "native_observability_alerts", "none", "no_legacy_handler", "Native alert surface."),
    RouteOwnership("GET", "/api/data-health", "FastAPI", "native_data_health", "mlb_app.routes.data_health.data_health", "delete", "Native data-health endpoint; service resolved from AppContainer."),
    RouteOwnership("GET", "/api/data-health/dashboard", "FastAPI", "native_data_health_dashboard", "mlb_app.routes.data_health.data_health_dashboard", "delete", "Native data-health dashboard endpoint; service resolved from AppContainer."),
    RouteOwnership("GET", "/api/data/status", "FastAPI", "native_data_status", "none", "no_legacy_handler", "Collector freshness/status endpoint; compact public health contract."),
    RouteOwnership("GET", "/api/runtime/collector-check", "FastAPI", "native_runtime_collector_check", "none", "no_legacy_handler", "Read-only daily collector verification endpoint."),
    RouteOwnership("GET", "/api/grading/health", "FastAPI", "native_grading_health", "mlb_app.routes.data_health.grading_health", "delete", "Native grading health endpoint; service resolved from AppContainer."),
    RouteOwnership("GET", "/api/workflows/health", "FastAPI", "native_workflow_health", "mlb_app.routes.workflows.workflow_health", "delete", "Native workflow health endpoint; service resolved from AppContainer."),
    RouteOwnership("GET", "/api/prop-ml/status", "FastAPI", "native_prop_ml_status", "mlb_app.routes.health.prop_ml_status", "delete", "Native prop-ML status endpoint; service resolved from AppContainer."),
)

NATIVE_OWNED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    (entry.method, entry.path) for entry in ROUTE_OWNERSHIP if entry.owner == "FastAPI"
)

TEMPORARY_LEGACY_ROUTES: frozenset[tuple[str, str]] = frozenset(
    (entry.method, entry.path) for entry in ROUTE_OWNERSHIP if entry.owner == "legacy-temporary"
)


def native_owned_paths() -> set[str]:
    return {path for _method, path in NATIVE_OWNED_ROUTES}
