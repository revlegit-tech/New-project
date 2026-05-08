# BoardCache — Phase 4 Hot-Path Latency

`mlb_app.services.board_cache.BoardCache` is the process-local cache for the EdgeBoard hot path.

## Purpose

The EdgeBoard route is a high-frequency UI polling path. It should not rebuild the full playerboard and model-card enrichment graph on every request when the source data has not changed.

The cache is intentionally conservative:

- 30-second default TTL.
- Thread-safe via `threading.RLock`.
- Per-key build locks to avoid duplicate rebuilds under concurrent requests.
- Deep-copy payload storage and retrieval to prevent mutation bleed.
- File dependency signatures using resolved path, existence, `mtime_ns`, and size.
- Automatic invalidation when the playerboard CSV changes.

## Cache key

The default EdgeBoard key is:

```python
(EDGE_BOARD_VERSION, season, date, market, limit)
```

This includes the query dimensions that affect the returned board payload. Refresh/save requests bypass serving from cache because they represent explicit operator intent.

## Dependency signatures

`EdgeBoardService` currently tracks the saved playerboard CSV:

```python
playerboard.playerboard_file(season)
```

If the pipeline appends or replaces that CSV, the changed file signature invalidates cached EdgeBoard payloads immediately, even before TTL expiry.

## Response metadata

Every EdgeBoard payload now exposes:

```json
{
  "boardCache": {
    "hit": true,
    "reason": "hit",
    "key": "(...)",
    "ageSeconds": 1.2,
    "ttlRemainingSeconds": 28.8,
    "dependencyCount": 1
  }
}
```

The existing top-level `cacheHit` boolean is preserved for compatibility. It is `true` when either the legacy saved-playerboard cache or the new BoardCache served a hit.

## Operational note

Under Gunicorn, each worker owns a process-local cache. This is acceptable for this phase because each worker independently checks the source CSV signature before serving cached content.
