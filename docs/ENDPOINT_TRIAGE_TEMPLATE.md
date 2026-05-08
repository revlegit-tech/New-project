# Endpoint Triage Table

Classification values:

- `PORT`: Required product behavior. Move to `mlb_app/routes -> services -> repositories` with the existing API contract preserved.
- `REPLACE`: Required behavior, but legacy implementation should be redesigned during migration.
- `RETIRE`: No longer needed. Remove only after confirming no frontend, CI job, workflow, script, or operator runbook calls it.
- `QUARANTINE`: Admin, training, sync, backfill, repair, paid-API, or mutation workflow. Move behind CLI, scheduler, internal-only API, or authenticated admin boundary.

| Endpoint | Method | app.py behavior | Current frontend/script caller | mlb_app equivalent | Classification | Mutation? | Risk level | Required guard | Owner | Status | Notes / acceptance test |
|---|---:|---|---|---|---|---:|---|---|---|---|---|
| `/api/app/status` | GET | Product/trust readiness summary | Trust surface | `mlb_app.routes.health.app_status` | PORT | No | Medium | Schema contract + request ID | TBD | In progress | Must show Research Only/Missing Data explicitly on malformed readiness. |
| `/api/edge-board` | GET | Main betting board payload | Outlier Today board | `mlb_app.routes.edge_board.edge_board` | PORT | No | High | Contract tests + BoardCache | TBD | In progress | Repeated requests must avoid full rebuild once BoardCache lands. |
| `/api/playerboard/health` | GET | Playerboard/data health check | Trust surface / model room | `mlb_app.routes.playerboard.playerboard_health` | PORT | No | Medium | Contract tests | TBD | In progress | No runtime imports on hot health path after Phase 4. |
| `/api/model-cards` | GET | Model readiness cards | Model room / trust surface | `mlb_app.routes.model_cards.model_cards` | PORT | No | High | Schema contract + no silent fallbacks | TBD | In progress | Production-eligible markets must be explicit. |
| `/api/data-health/dashboard` | GET | Data health dashboard | Model room / trust surface | `mlb_app.routes.data_health.data_health_dashboard` | PORT | No | High | Schema contract + explicit stale/missing data state | TBD | In progress | Must distinguish stale, partial, missing, inconsistent. |
| `/api/my-picks` | POST | Create tracked user pick | My Picks | `mlb_app.routes.my_picks.create_pick` | PORT | Yes | High | Action header + auth/rate limit/audit | TBD | Not started | Static action header alone is not authentication. |
| `/api/bankroll/settings` | POST | Update bankroll settings | My Picks / bankroll panel | `mlb_app.routes.my_picks.update_bankroll_settings` | PORT | Yes | High | Action header + auth/rate limit/audit | TBD | Not started | Atomic write path required. |
| `/api/weather/sync` | POST | Trigger weather sync | Admin/script | None yet | QUARANTINE | Yes | High | Admin CLI or authenticated internal endpoint | TBD | Not started | Must not be bettor-facing. |
| `/api/savant/sync` | POST | Trigger Savant sync | Admin/script | None yet | QUARANTINE | Yes | High | Admin CLI or authenticated internal endpoint | TBD | Not started | May call external service and mutate cache. |
| `/api/model-data/refresh` | POST | Refresh model data files | Admin/script | None yet | REPLACE | Yes | Critical | Job boundary + auth/rate limit/request ID | TBD | Not started | Should not run inside normal product request path. |
| `/api/pipeline/train-strikeouts` | POST | Start model training | Admin/script | None yet | QUARANTINE | Yes | Critical | CLI/job queue/authenticated admin only | TBD | Not started | Expensive state-mutating workflow. |
| `/api/predictions/grade` | POST | Grade stored predictions | Admin/script | None yet | REPLACE | Yes | Critical | Job boundary + auth/rate limit/request ID | TBD | Not started | Must log grading freshness and failures. |
