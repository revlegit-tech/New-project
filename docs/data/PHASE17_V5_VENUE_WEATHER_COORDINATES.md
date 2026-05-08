# Phase 17 v5 — Venue Weather Coordinates

This patch adds a canonical MLB venue coordinate file for Open-Meteo weather enrichment.

## Source of truth

`data/reference/mlb_venue_coordinates.csv`

The file contains 30 team venue rows and includes venue aliases so schedule venue names can be normalized more reliably.

## Operating commands

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path

python .\tools\phase17_refresh_venue_coordinates.py --write
python .\tools\phase17_patch_openmeteo_coordinate_loader.py --write

$Date = "2026-05-07"
python .\tools\run_phase17_context_from_apis.py --date $Date --season 2026 --markets batter_hits batter_total_bases --line-source propline
python .\tools\phase17_game_context_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
```

## Trust rules

- Weather is fetched only when a venue has a real latitude/longitude.
- Missing coordinates remain Missing Data.
- Game totals and implied runs still require real line data; the coordinate patch does not fabricate them.
