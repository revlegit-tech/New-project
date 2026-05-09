# Phase 9 — FastAPI / ASGI Migration Scaffold

This cumulative overlay adds an experimental FastAPI runtime while keeping
Gunicorn/WSGI canonical.

## New files

- `mlb_app/asgi.py`
- `requirements.phase9-addition.txt`
- `docs/runtime/ASGI_MIGRATION.md`
- `tests/test_asgi_migration.py`

## Commands

Canonical runtime:

```bash
make serve
```

Experimental ASGI runtime:

```bash
make serve-asgi
```

ASGI-only smoke tests:

```bash
make smoke-asgi
```

## Contract rule

No frontend payload shapes should change in this phase. FastAPI delegates to the
existing route/service/repository path and offloads sync work to a worker thread.
