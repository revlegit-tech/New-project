# Phase 5 start — Repository CSV caching

This cumulative overlay extends Phase 4 hot-path latency work into the repository layer.

## Included changes

- Adds `CsvStore.read_rows_cached(path, max_age_seconds=60)`.
- Uses resolved-path cache keys.
- Invalidates on TTL expiry or `(mtime_ns, size)` file-signature changes.
- Protects cache state with a class-level `threading.RLock`.
- Returns deep copies so service code cannot mutate cached rows.
- Makes `write_rows()` temp-file + `os.replace()` atomic.
- Invalidates the written path after successful writes.
- Refactors `ModelCardService` backtest reads to use cached CSV access.
- Refactors `ModelRegistryService` training stats reads to use cached CSV access.
- Adds unit tests for hits, TTL expiry, mtime invalidation, count reuse, and write invalidation.

## Validation

Run:

```bash
python -m pytest \
  tests/test_csv_store.py \
  tests/test_model_card_service.py \
  tests/test_prop_detail_service.py \
  tests/test_edge_board_service.py \
  tests/test_board_cache.py \
  tests/test_wsgi_smoke.py \
  tests/test_request_observability.py \
  tests/test_cache_store.py \
  tests/test_static_file_guard.py \
  tests/test_security_export.py \
  tests/test_trust_surface_static_safety.py \
  -q
```

In this environment the suite was validated in two groups:

```bash
python -m pytest tests/test_csv_store.py tests/test_model_card_service.py tests/test_prop_detail_service.py tests/test_edge_board_service.py -q
python -m pytest tests/test_board_cache.py tests/test_wsgi_smoke.py tests/test_request_observability.py tests/test_cache_store.py tests/test_static_file_guard.py tests/test_security_export.py tests/test_trust_surface_static_safety.py -q
```

Results: 16 passed and 27 passed.
