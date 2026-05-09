# MLB App Architecture

## Production boundary

`mlb_app/` is the canonical production application boundary. Product behavior that is served to users must live under `mlb_app/` or in an explicit package imported by `mlb_app/`.

Dependency direction rule:

- Allowed: root-level scripts and tools import from `mlb_app`.
- Forbidden: `mlb_app` imports from root-level operational scripts.

Sprint 2 moved playerboard schema, repository, and builder ownership under `mlb_app/contracts`, `mlb_app/repositories`, and `mlb_app/services`. Sprint 4 introduces `mlb_app.api` as the native FastAPI route layer while retaining a legacy fallback gateway for routes that have not yet been migrated.

## Runtime modes

| Mode | Entrypoint | Status | Purpose |
| --- | --- | --- | --- |
| Production-style WSGI | `mlb_app.wsgi:application` via Gunicorn | Canonical | Bounded worker runtime for deployment-like operation. |
| Local development | `python -m mlb_app.server` / `make run` | Supported | Fast local feedback with the same `mlb_app` runtime boundary. |
| ASGI native API | `mlb_app.asgi:app` / `make serve-asgi` | Supported migration target | Native FastAPI routes for high-traffic product endpoints with a legacy fallback gateway for unmigrated routes. |
| Root scripts | `playerboard.py`, collectors, trainers, repair utilities | Operational / legacy | CLI wrappers, collectors, diagnostics, migrations, or historical utilities only. |

## Source tree policy

The repository should make production code visually distinct from tools and history:

```text
mlb_app/                  # canonical production runtime
frontend/                 # future bundled UI source
tests/                    # automated tests
tools/                    # operational CLIs, diagnostics, collectors, cleanup utilities
docs/changelog/phases/    # historical phase notes
docs/changelog/stages/    # historical stage notes
docs/changelog/patches/   # old patch files and integration patch notes
requirements/             # layered inputs and deterministic lockfiles
```


## Native FastAPI route layer

Sprint 4 route ownership lives under `mlb_app/api/`:

```text
mlb_app/api/
  app.py                 # FastAPI app factory, native router registration, legacy fallback
  dependencies.py        # container/service dependency providers
  middleware.py          # request metadata/access logging and security headers
  models.py              # Pydantic response models that preserve existing JSON contracts
  routes/
    status.py
    edge_board.py
    playerboard.py
    prop_detail.py
    model_cards.py
    picks.py
    health.py
```

Native routes must use injected services from `AppContainer`; they should not instantiate service graphs per request. Blocking CSV/model-file reads remain isolated behind service/repository calls and are invoked from async routes with `asyncio.to_thread()` until the data source is fully DB-backed or cached.

## Mutable state policy

CSV remains an interchange/export format. App-owned mutable state such as user picks, bankroll settings, and prediction events is backed by the transactional SQLite WAL layer introduced in Sprint 3. Future collector runs and grading records should follow the same repository pattern.

## Current season policy

The runtime season is configured centrally through `Settings.current_season`:

1. `MLB_CURRENT_SEASON` if set.
2. The active MLB season fallback from `mlb_app.config.active_mlb_season()`.

Services should derive year-suffixed paths from this setting or from an explicit request query parameter. Do not hardcode a season in service defaults.

## Deprecation list

- Root phase/stage markdown and patch files are archived under `docs/changelog/`.
- Root `check_*`, `inspect_*`, and `patch_*` scripts are no longer root entrypoints and live under `tools/`.
- In-tree backup files such as `*.phase*_backup*`, `*.backup*`, and generated playerboard header-mismatch CSVs are not source files.
- The legacy ASGI handler adapter remains only as a fallback for unmigrated routes. High-traffic board, playerboard, prop-detail, picks, bankroll, model-card, and app-status endpoints are native FastAPI routes under `mlb_app/api/routes/`.
