# ADR 0001: `mlb_app.asgi:app` is the production entrypoint

Date: 2026-05-09

## Status

Accepted.

## Context

The application was in a migration architecture with both WSGI and ASGI paths. That allowed behavior drift across service construction, caching, response contracts, mutation security, and route ownership.

## Decision

Production serves `mlb_app.asgi:app` through Gunicorn with Uvicorn workers:

```bash
gunicorn mlb_app.asgi:app -k uvicorn.workers.UvicornWorker --workers ${GUNICORN_WORKERS:-4} --bind 0.0.0.0:${PORT:-8765} --timeout ${GUNICORN_TIMEOUT:-30} --access-logfile -
```

The ASGI app is created by `mlb_app.api.app:create_app`, stores one `AppContainer` at `app.state.container`, and routes native product endpoints through application-scoped services.

## Consequences

- `make serve` uses ASGI/Gunicorn.
- `make serve-wsgi-legacy` exists only for compatibility diagnostics.
- New route work is frozen in `mlb_app/routes/*`.
- High-traffic betting endpoints are removed from the legacy router.
- Native response models must use strict Pydantic contracts; `extra="allow"` is disallowed.
