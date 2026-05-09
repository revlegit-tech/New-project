# app.py Retirement

Phase 10 removes the root `app.py` entrypoint from the production source tree.

## Current runtime commands

Local development:

```bash
make run
```

Production ASGI/Gunicorn runtime:

```bash
make serve
```

Local ASGI developer runtime:

```bash
make serve-asgi-local
```

Live smoke check against a running server:

```bash
make smoke-live
```

Retirement guard:

```bash
make validate-retirement
```

## Browser URLs

Canonical UI:

```text
http://127.0.0.1:8765
```

Runtime-isolated Outlier UI:

```text
http://127.0.0.1:8765/?view=outlier
```

Core health/status endpoints:

```text
http://127.0.0.1:8765/api/app/status
http://127.0.0.1:8765/api/edge-board
http://127.0.0.1:8765/api/playerboard/health
http://127.0.0.1:8765/api/model-cards
http://127.0.0.1:8765/api/data-health/dashboard
```

## Production boundary

`mlb_app/` is now the only shipped application boundary. Production enters through `mlb_app.asgi:app`; the root legacy entrypoint has no Makefile target, no Docker entrypoint, and no CI smoke path.

Historical endpoint mapping remains in `docs/endpoint-triage/` for auditability. New product behavior must land in:

```text
mlb_app/api/routes/
mlb_app/services/
mlb_app/repositories/
mlb_app/schemas/
public/outlier-*.js
```

## Validation rule

`tools/validate_app_py_retirement.py` fails if:

- root `app.py` exists
- production commands instruct `python app.py`
- `run-legacy` returns to the Makefile
- CI production workflows compile or invoke `app.py`
- README/developer commands point developers back to the retired entrypoint
