# Phase 9 ASGI Migration Scaffold

`mlb_app.wsgi:application` remains the canonical production runtime. Phase 9 adds
`mlb_app.asgi:app` as a contract-matched sidecar runtime so we can compare FastAPI
behavior without rewriting the service layer or changing frontend payloads.

## Run

```bash
make serve-asgi
```

Equivalent command:

```bash
uvicorn mlb_app.asgi:app --host 0.0.0.0 --port 8765
```

## Design

FastAPI routes are thin adapters:

```text
FastAPI route
  -> anyio.to_thread.run_sync(existing sync router/service path)
  -> existing JSON response contract
```

This keeps blocking CSV/JSON file I/O off the ASGI event loop while preserving the
WSGI response shape.

## Canonical runtime status

Use this for production-style serving until ASGI parity is intentionally promoted:

```bash
make serve
```

That command still runs:

```bash
gunicorn mlb_app.wsgi:application
```

## Promotion gate

Do not make ASGI canonical until:

- core endpoint response contracts match WSGI;
- blocking repository I/O is offloaded or async-safe;
- mutation security tests pass under ASGI;
- frontend runtime loads unchanged;
- route-level observability emits request IDs and structured logs.
