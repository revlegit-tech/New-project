# Phase 3 — Cumulative Production Server Promotion and Observability

This bundle is cumulative through Phase 3:

- Phase 0: `mlb_app` canonical runtime, Gunicorn entrypoint, legacy `app.py` escape hatch.
- Phase 1: endpoint parity and legacy triage inventory.
- Phase 2: Sprint 0 safety patches: trust-surface XSS guard, static path guard, atomic JSON/cache writes, safe export.
- Phase 3: production serving observability: request IDs, structured access logs, middleware shell, and WSGI/Gunicorn smoke wiring.

## New Phase 3 files

| File | Purpose |
|---|---|
| `mlb_app/middleware.py` | Request ID generation, client IP extraction helpers, structured access log event model. |
| `mlb_app/http.py` | Adds `X-Request-Id` from the central response helper. |
| `mlb_app/routing.py` | Logs routed API requests at the dispatch boundary. |
| `mlb_app/wsgi.py` | Carries request metadata through the Gunicorn/WSGI adapter. |
| `mlb_app/server.py` | Carries request metadata through the local dev server and static responses. |
| `tests/test_request_observability.py` | Verifies request ID headers, inbound ID sanitation, static IDs, and structured JSON logs. |
| `.github/workflows/mlb_app_smoke.yml` | CI example that boots Gunicorn and smokes canonical endpoints. |
| `docs/observability/REQUEST_IDS_AND_ACCESS_LOGS.md` | Operator/developer notes for the request correlation contract. |

## Runtime commands

```bash
make run          # local dev, mlb_app only
make serve        # Gunicorn production-style runtime
make run-legacy   # app.py escape hatch only
```

## Validation performed

```bash
python -m pytest \
  tests/test_wsgi_smoke.py \
  tests/test_static_file_guard.py \
  tests/test_cache_store.py \
  tests/test_security_export.py \
  tests/test_trust_surface_static_safety.py \
  tests/test_request_observability.py \
  -q
```

Result: `21 passed`.

## Notes

The test environment used for building this bundle did not have `gunicorn` preinstalled, so live Gunicorn boot validation should run after installing `requirements.txt`. The WSGI callable itself is covered by direct WSGI tests, and the CI workflow included here performs the live Gunicorn smoke when dependencies are installed.
