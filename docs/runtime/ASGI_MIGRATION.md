# ASGI Runtime Consolidation

`mlb_app.asgi:app` is the canonical production runtime. It builds the native FastAPI app through `mlb_app.api.app:create_app`, installs an application-scoped `AppContainer`, and registers high-traffic product endpoints as native FastAPI routes.

## Production command

```bash
make serve
```

Equivalent command:

```bash
gunicorn mlb_app.asgi:app \
  -k uvicorn.workers.UvicornWorker \
  --workers ${GUNICORN_WORKERS:-4} \
  --bind 0.0.0.0:${PORT:-8765} \
  --timeout ${GUNICORN_TIMEOUT:-30} \
  --access-logfile -
```

## Local ASGI command

```bash
make serve-asgi-local
```

Equivalent command:

```bash
uvicorn mlb_app.asgi:app --host 0.0.0.0 --port 8765
```

## Legacy compatibility command

```bash
make serve-wsgi-legacy
```

This command exists only for compatibility diagnostics. It is not a production runtime. FastAPI-owned routes such as `/api/app/status`, `/api/edge-board`, `/api/playerboard`, `/api/prop-detail`, `/api/model-cards`, `/api/my-picks`, `/api/bankroll/settings`, `/api/exposure/summary`, and `/api/admin/propline/props/sync` are intentionally absent from the legacy router.

## Route ownership gate

```bash
make validate-route-ownership
```

The gate fails if FastAPI-owned endpoints are reintroduced into `mlb_app.server.build_router()` or if native route names disappear from the ASGI app.
