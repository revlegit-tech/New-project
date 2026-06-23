# Local Launch

Use the Windows launcher from the repository root:

```powershell
.\scripts\start_mlb_app.ps1
.\scripts\start_mlb_app.ps1 -SkipBootstrap
.\scripts\start_mlb_app.ps1 -NoBrowser
.\scripts\start_mlb_app.ps1 -Port 8765 -Host 127.0.0.1 -Date today
```

The launcher sets safe local defaults only when the variables are missing:

- `PYTHONPATH`
- `DB_ENABLED`
- `DB_FALLBACK_TO_CSV`
- `DATABASE_URL`
- `GAME_MARKET_ENRICHMENT_ENABLED`
- `TEAM_GAME_MARKET_PROJECTIONS_ENABLED`

Bootstrap is intentionally lightweight. It may check freshness, read status files, collect a current-day ActionNetwork snapshot when missing or stale, and write `data/status/launch_bootstrap_status.json`. It must not train, promote, backfill historical ActionNetwork data, or run long postgame validation.

FastAPI starts as `mlb_app.asgi:app`; collectors and workflows stay in scripts.
