# Post-Phase 10 Data-Fresh Detail Hotfix

This overlay fixes two issues after the Outlier UI split:

1. **Stale/different-day props mixing into the board**
   - Playerboard now auto-prefers the canonical `data/odds/propline_props_YYYY-MM-DD.csv` source when it exists.
   - Legacy prototype prop files are no longer silently blended into a dated board when a canonical PropLine export exists.
   - `playerboard.py --replace-date --source-mode canonical` removes old rows for the slate before saving fresh rows.
   - `tools/refresh_outlier_slate.py` fetches PropLine and rebuilds the board in one command.

2. **Advanced prop detail hit-rate UI**
   - Playerboard rows now carry backend-computed hit-rate windows: L5, L10, L20, H2H, current season, previous season.
   - Prop detail exposes `trendProfile` from cached StatsAPI game logs.
   - The advanced detail modal renders a hit-rate profile and recent-game graph.
   - Existing Outlier row clickthrough behavior is preserved.

## Recommended refresh command

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python .\tools\refresh_outlier_slate.py --date $Date --season 2026 --limit 500 --source-mode canonical
```

If your local script version does not accept `--source-mode`, use:

```powershell
python .\tools\refresh_outlier_slate.py --date $Date --season 2026 --limit 500
```

## Manual equivalent

```powershell
python .\tools\fetch_propline_props.py --date $Date --max-events 0
python .\playerboard.py --season 2026 --date $Date --limit 500 --market "" --replace-date --source-mode canonical
```

Then restart:

```powershell
python -m mlb_app.server 8765 --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:8765/?view=outlier
```


## v2 fix

Adds missing `write_csv_rows()` helper used by `prune_playerboard_snapshot()` during replace-date rebuilds.
