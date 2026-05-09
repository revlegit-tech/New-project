# Phase 4 — Hot-Path Latency: BoardCache

This cumulative overlay includes Phase 0 through Phase 3 artifacts plus the Phase 4 BoardCache implementation.

## Added

- `mlb_app/services/board_cache.py`
- `mlb_app/services/edge_board_service.py`
- `tests/test_board_cache.py`
- `docs/performance/BOARD_CACHE.md`
- `phase4_board_cache.patch`

## Behavior

`EdgeBoardService` now uses a process-local `BoardCache` before rebuilding the EdgeBoard payload. The cache:

- keys by `EDGE_BOARD_VERSION`, season, date, market, and limit;
- expires entries after 30 seconds by default;
- invalidates immediately when the saved playerboard CSV changes mtime or size;
- uses per-key locks to avoid duplicate expensive builds;
- returns deep copies so callers cannot mutate cached payloads;
- exposes honest `boardCache` metadata in API responses.

Refresh/save query requests bypass serving from cache, then store the fresh result for subsequent normal reads.

## Validation

Run:

```bash
python -m pytest \
  tests/test_board_cache.py \
  tests/test_wsgi_smoke.py \
  tests/test_request_observability.py \
  tests/test_cache_store.py \
  tests/test_static_file_guard.py \
  tests/test_security_export.py \
  tests/test_trust_surface_static_safety.py \
  -q
```

Validated in this workspace: `27 passed`.
