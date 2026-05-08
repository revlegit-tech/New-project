# Phase 6 — Mutation Endpoint Security

State-changing endpoints are protected at the `mlb_app` routing boundary, not inside individual route handlers. The legacy `X-Baseball-Prop-Action: 1` header remains as an operator/user intent signal, but it is no longer treated as authentication for shared or production runtimes.

## Protected endpoints currently registered in `mlb_app`

| Endpoint | Method | Owner | Risk | Middleware kind |
|---|---|---:|---:|---|
| `/api/my-picks` | POST | bettor_state | MEDIUM | `pick_write` |
| `/api/my-picks/update` | POST | bettor_state | MEDIUM | `pick_write` |
| `/api/bankroll/settings` | POST | risk_controls | HIGH | `bankroll_write` |

All future sync, training, backfill, grading, refresh, repair, upload, or paid external API endpoints must be registered with `mutation=True` or kept out of the product router entirely.

## Runtime policy

| Runtime | Required controls |
|---|---|
| local / development | `X-Baseball-Prop-Action: 1` + loopback client IP. Unconfigured developer machines default to this mode to preserve local workflows while still rejecting remote mutation calls. |
| staging / shared | `X-Baseball-Prop-Action: 1` + configured mutation token + token-bucket rate limit. |
| production | `X-Baseball-Prop-Action: 1` + configured mutation token + optional/required CSRF token + token-bucket rate limit. |

Environment variables: `MLB_ENV`, `MLB_DEV_MODE`, `MLB_MUTATION_TOKEN`, `MLB_API_TOKEN`, `MLB_ADMIN_TOKEN`, `MLB_CSRF_TOKEN`, `MLB_REQUIRE_CSRF`, `MLB_MUTATION_RATE_LIMIT`, `MLB_MUTATION_RATE_WINDOW_SECONDS`.

Accepted token headers: `X-MLB-App-Token`, `X-API-Token`, or `Authorization: Bearer <token>`.

A process-local token bucket enforces the default mutation policy: **10 mutation requests per minute per client IP per route**. On denial, the API returns `429` with `Retry-After`. Mutation access logs include `mutation`, `rate_limited`, and `auth_mode` fields.

## Quarantine rule

Do not port legacy admin/workflow endpoints directly into the product API. Anything that writes cache files, trains models, grades predictions, triggers sync/backfill/catchup, imports data, repairs data, or calls paid external APIs must move to a CLI command, scheduled workflow, admin-only route, or internal worker command.

See `docs/security/mutation_endpoint_inventory.csv` for the current triage-generated list.
