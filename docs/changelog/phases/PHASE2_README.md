# Phase 2 Cumulative Artifacts — Sprint 0 Security and Safety

This bundle is cumulative. It includes:

- Phase 0 canonical runtime overlay: `Makefile`, `Dockerfile`, `mlb_app/wsgi.py`, legacy banner guidance, and safe export command wiring.
- Phase 1 endpoint triage artifacts: inventory, classification queues, and triage generator.
- Phase 2 Sprint 0 safety patches: trust-surface safe DOM rendering, JSON/cache atomic writes, static-file symlink guard, export enforcement, and tests.

## Apply order

Copy the files in this overlay into the project root, preserving paths.

```bash
cp -R phase2_cumulative_artifacts/* /path/to/project/
```

Then manually paste `app_py_legacy_banner.txt` at the top of `app.py` if it has not already been applied.

## Key behavior changes

### Runtime

- `make run` starts `python -m mlb_app.server`.
- `make serve` starts `gunicorn mlb_app.wsgi:application`.
- `make run-legacy` is the only Makefile path for `app.py`.
- Docker boots `mlb_app.wsgi:application` via Gunicorn and health-checks `/api/app/status`.

### Trust surface

`public/trust-surface.js` no longer uses `innerHTML` or `insertAdjacentHTML` for API-sourced payload fields. It builds DOM nodes with `document.createElement()` and writes text through `textContent`.

It also validates the trust-surface contract before rendering:

- `productState: string`
- `grading.state: string`
- `dataConfidence: string`
- `productionEligibleMarkets: array`
- `latestBoardDate` or equivalent playerboard date

Malformed payloads render a conservative `Research Only` state and log a warning.

### JSON/cache safety

`CacheStore` is now a compatibility wrapper around `JsonStore`. `JsonStore` provides:

- per-path `threading.RLock`
- temp-file write
- `fsync`
- atomic `os.replace`
- dev-mode strict corruption surfacing via `MLB_DEV_MODE=1` or `MLB_STRICT_JSON_READS=1`

### Static files

`mlb_app/server.py` now centralizes static path resolution in `resolve_static_target()` and rejects traversal/symlink escapes using `target.is_relative_to(public_root)`. `mlb_app/wsgi.py` shares the same helper.

### Safe export

`tools/export_project.py` now excludes:

- `data/cache/**`
- `__pycache__/**`
- `*.pyc`, `*.pyo`
- `.en`, `.env`, `.env.*`, `*.env`
- nested archive artifacts such as `*.zip`, `*.tar`, `*.tgz`, `*.rar`, `*.7z`

It also fails and deletes the output archive if the generated ZIP exceeds the configured threshold.

## Validation run

Executed successfully in the extracted project:

```bash
python -m pytest \
  tests/test_wsgi_smoke.py \
  tests/test_static_file_guard.py \
  tests/test_cache_store.py \
  tests/test_security_export.py \
  tests/test_trust_surface_static_safety.py \
  -q
```

Result: `15 passed`.

## Included files

- `phase2_cumulative.patch` — unified patch for the changed code/test files.
- `Makefile`
- `Dockerfile`
- `requirements.txt`
- `mlb_app/wsgi.py`
- `mlb_app/server.py`
- `mlb_app/repositories/json_store.py`
- `mlb_app/repositories/cache_store.py`
- `public/trust-surface.js`
- `tools/export_project.py`
- `tools/safe_export.py`
- `tools/smoke_mlb_app.py`
- `tools/generate_endpoint_triage.py`
- `tests/test_wsgi_smoke.py`
- `tests/test_static_file_guard.py`
- `tests/test_cache_store.py`
- `tests/test_security_export.py`
- `tests/test_trust_surface_static_safety.py`
- `tests/e2e/trust-surface-xss.spec.js`
- `docs/endpoint-triage/*`
- Phase 0 and Phase 1 README/template files

## Not performed by code

Credential rotation cannot be completed from this artifact. The patch enforces safer export behavior and tracked-secret checks, but the actual provider-side revoke/regenerate/update-secret workflow still requires operator access.
