# Route Ownership Matrix

Runtime truth: `mlb_app.asgi:app -> create_app -> AppContainer -> services -> repositories -> snapshots/state`.

FastAPI-owned routes must be implemented under `mlb_app/api/routes/*`, must get services through `mlb_app.api.dependencies.get_container`, and must not instantiate services directly inside handlers. Legacy handlers listed below are deletion targets, not production owners.

| Method | Endpoint | Owner | Native route name | Legacy handler | Legacy action | Notes |
|---|---|---|---|---|---|---|
| GET | `/api/app/status` | FastAPI | `native_app_status` | `mlb_app.routes.health.app_status` | delete after parity | Canonical app/product status. |
| GET | `/api/edge-board` | FastAPI | `native_edge_board` | `mlb_app.routes.edge_board.edge_board` | delete | High-traffic board path; no legacy fallback. |
| GET | `/api/playerboard` | FastAPI | `native_playerboard` | `mlb_app.routes.playerboard.playerboard` | delete after contract parity | Board payload from `AppContainer.playerboard_service`. |
| GET | `/api/playerboard/health` | FastAPI | `native_playerboard_health` | `mlb_app.routes.playerboard.playerboard_health` | delete after health parity | Health contract from native service. |
| GET | `/api/prop-detail` | FastAPI | `native_prop_detail` | `mlb_app.routes.prop_detail.prop_detail` | delete after targeted lookup | Route is native now; Sprint 3 indexes lookup by `propKey`. |
| GET | `/api/model-cards` | FastAPI | `native_model_cards` | `mlb_app.routes.model_cards.model_cards` | delete after model cache hardening | Model room list. |
| GET | `/api/model-card` | FastAPI | `native_model_card` | `mlb_app.routes.model_cards.model_card` | delete after model cache hardening | Single model-card query endpoint. |
| GET | `/api/model-cards/{market}` | FastAPI | `native_model_card_by_market` | `mlb_app.routes.model_cards.model_card` | delete after model cache hardening | Parameterized model-card detail. |
| GET | `/api/my-picks` | FastAPI | `native_my_picks` | `mlb_app.routes.my_picks.my_picks` | delete after mutation parity | Picks read. |
| POST | `/api/my-picks` | FastAPI | `native_create_pick` | `mlb_app.routes.my_picks.create_pick` | delete after mutation parity | Native mutation security. |
| POST | `/api/my-picks/update` | FastAPI | `native_update_pick` | `mlb_app.routes.my_picks.update_pick` | delete after mutation parity | Native mutation security. |
| GET | `/api/bankroll/settings` | FastAPI | `native_bankroll_settings` | `mlb_app.routes.my_picks.bankroll_settings` | delete after mutation parity | Bankroll/risk settings. |
| POST | `/api/bankroll/settings` | FastAPI | `native_update_bankroll_settings` | `mlb_app.routes.my_picks.update_bankroll_settings` | delete after mutation parity | Native mutation security. |
| GET | `/api/exposure/summary` | FastAPI | `native_exposure_summary` | `mlb_app.routes.my_picks.exposure_summary` | delete after parity | Exposure summary. |
| POST | `/api/admin/propline/props/sync` | FastAPI | `native_admin_sync_propline_props` | `mlb_app.routes.propline.sync_props` | delete | Admin-only paid API sync; no generic fallback. |
| GET | `/api/prediction-events` | FastAPI | `native_prediction_events` | `none` | no legacy handler | Prediction audit event stream. |
| POST | `/api/prediction-events` | FastAPI | `native_record_prediction_event` | `none` | no legacy handler | Prediction audit write with native mutation security. |
| GET | `/api/observability/metrics` | FastAPI | `native_observability_metrics` | `none` | no legacy handler | Native metrics surface. |
| GET | `/api/observability/alerts` | FastAPI | `native_observability_alerts` | `none` | no legacy handler | Native alert surface. |
| GET | `/api/data-health` | legacy-temporary | `todo_native_data_health` | `mlb_app.routes.data_health.data_health` | migrate next | Explicit fallback only. |
| GET | `/api/data-health/dashboard` | legacy-temporary | `todo_native_data_health_dashboard` | `mlb_app.routes.data_health.data_health_dashboard` | migrate next | Explicit fallback only. |
| GET | `/api/grading/health` | legacy-temporary | `todo_native_grading_health` | `mlb_app.routes.data_health.grading_health` | migrate next | Explicit fallback only. |
| GET | `/api/workflows/health` | legacy-temporary | `todo_native_workflow_health` | `mlb_app.routes.workflows.workflow_health` | migrate next | Explicit fallback only. |
| GET | `/api/prop-ml/status` | legacy-temporary | `todo_native_prop_ml_status` | `mlb_app.routes.health.prop_ml_status` | migrate next | Explicit fallback only. |

## CI guard

Run:

```bash
make validate-route-ownership
```

The guard fails when a FastAPI-owned route is registered in `mlb_app.server.build_router()` or when native route names disappear from `mlb_app.asgi:app`.
