# CsvStore mtime-aware cache

`mlb_app.repositories.csv_store.CsvStore` is now the canonical CSV repository boundary for service-layer reads.

## Goals

- Avoid repeated full CSV materialization on hot service paths.
- Invalidate automatically when pipeline outputs update a CSV.
- Preserve correctness by returning deep copies to callers.
- Keep local file I/O safe enough for the current file-backed production model.

## Cache key and invalidation

Cache entries are keyed by the resolved CSV path. Each entry stores:

- row payload
- resolved path
- `st_mtime_ns`
- file size
- load timestamp
- TTL
- hit count

A cached read is served only when:

1. the TTL has not expired;
2. the current `(mtime_ns, size)` signature matches the cached signature;
3. the caller is using the same `max_age_seconds` policy.

Default TTL is 60 seconds for repository reads.

## API

```python
store = CsvStore()
rows = store.read_rows_cached(path, max_age_seconds=60)
count = store.count_rows(path)
CsvStore.invalidate(path)
CsvStore.invalidate()  # clear all
status = CsvStore.status()
```

`read_rows(path)` remains as a compatibility wrapper and uses `read_rows_cached(path)` by default.

## Writes

`write_rows()` writes to a temp file in the same directory, flushes/fsyncs the file, and then atomically replaces the target with `os.replace()`. The target cache entry is invalidated after a successful write.

## Service adoption

- `ModelCardService` uses cached CSV reads for backtest summaries.
- `ModelRegistryService` uses cached CSV reads for training stats.
- Existing services that still call `read_rows()` also benefit from the default cached path.

## Trust-surface rule

This cache must never hide missing or stale data. Services remain responsible for reporting `Missing Data`, `Research Only`, or stale-state messages when required inputs are absent or unproven.
