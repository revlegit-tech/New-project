# Sprint 4 — Native API Migration

## Objective

Move primary product endpoints from the transitional ASGI handler adapter to native FastAPI routes while preserving the existing JSON contracts used by the current UI.

## Implemented structure

```text
mlb_app/
  api/
    app.py
    dependencies.py
    middleware.py
    models.py
    routes/
      status.py
      edge_board.py
      playerboard.py
      prop_detail.py
      model_cards.py
      picks.py
      health.py
  container.py
```

## Native routes

The following routes are now registered before the legacy `/api/{api_path:path}` gateway:

| Route | Service boundary | Notes |
| --- | --- | --- |
| `GET /health/live` | process health | Liveness only. |
| `GET /health/ready` | DB/container readiness | Confirms migrations and service container wiring. |
| `GET /api/app/status` | `AppStatusService` | Native trust/status surface. |
| `GET /api/edge-board` | `EdgeBoardService` | Main board endpoint, offloaded with `asyncio.to_thread()`. |
| `GET /api/playerboard` | `PlayerboardService` | Contract-backed playerboard payload. |
| `GET /api/playerboard/health` | `PlayerboardService` | Schema and freshness health. |
| `GET /api/prop-detail` | `PropDetailService` | Detail rail payload. |
| `GET /api/model-cards` | `ModelCardService` | Model readiness cards. |
| `GET /api/model-card` | `ModelCardService` | Compatibility alias with market query support. |
| `GET /api/my-picks` | `PicksService` | SQLite-backed picks. |
| `POST /api/my-picks` | `PicksService` | Native mutation security enforced. |
| `POST /api/my-picks/update` | `PicksService` | Native mutation security enforced. |
| `GET /api/bankroll/settings` | `BankrollService` | SQLite-backed bankroll settings. |
| `POST /api/bankroll/settings` | `BankrollService` | Native mutation security enforced. |
| `GET /api/exposure/summary` | `PicksService` | Exposure from SQLite-backed picks/settings. |

## Compatibility strategy

`mlb_app.asgi:app` now uses `mlb_app.api.app.create_app()` and installs the legacy gateway after native routers. Unmigrated routes continue to work through `_dispatch_api_sync()`, but migrated routes bypass `RequestContext`, fake handler adapters, and `json_response()`.

## Security and observability

- `SecurityHeadersMiddleware` adds CSP report-only, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy` to API and static responses.
- `RequestMetadataMiddleware` normalizes request IDs, returns `X-Request-Id`, and emits structured access logs for native routes.
- Native mutating routes reuse the existing mutation policy: `X-Baseball-Prop-Action: 1`, loopback requirement for local mode, optional configured token enforcement for shared/staging/production, and rate limiting.

## Tests

Added `tests/test_sprint4_native_api.py` to verify:

1. Native health route and security headers.
2. Native route precedence before the legacy gateway.
3. SQLite-backed native bankroll and pick writes through the shared app container.

Validation command:

```bash
PYTHONPATH=. pytest -q
```
