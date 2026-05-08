# Phase 4 Continuation — PropDetail and ModelSnapshot Hot-Path Refactor

This cumulative overlay includes Phase 0 through Phase 4 BoardCache, plus the Phase 4 continuation patches:

- `PropDetailService` now reuses cached EdgeBoard rows and embedded `modelCard` context.
- `ModelCardService` now uses a thread-safe, mtime-aware `ModelSnapshotCache` for registry, grading, and backtest inputs.
- `PlayerboardService` moved hot-path `playerboard` imports to module scope with an explicit runtime error if required symbols are unavailable.
- Tests cover PropDetail embedded-model reuse, ModelSnapshot TTL reuse, and mtime invalidation.

## Validation

```bash
python -m pytest \
  tests/test_board_cache.py \
  tests/test_model_card_service.py \
  tests/test_prop_detail_service.py \
  tests/test_edge_board_service.py \
  tests/test_wsgi_smoke.py \
  tests/test_request_observability.py \
  tests/test_cache_store.py \
  tests/test_static_file_guard.py \
  tests/test_security_export.py \
  tests/test_trust_surface_static_safety.py \
  -q
```

Expected result from this build: `38 passed`.
