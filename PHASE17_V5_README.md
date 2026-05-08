# Phase 17 v5 — Venue Weather Coordinates

Adds canonical coordinates for all 30 MLB venues to improve Open-Meteo weather enrichment.

Files added:

- `data/reference/mlb_venue_coordinates.csv`
- `tools/phase17_refresh_venue_coordinates.py`
- `tools/phase17_patch_openmeteo_coordinate_loader.py`
- `tests/test_phase17_venue_coordinates.py`
- `docs/data/PHASE17_V5_VENUE_WEATHER_COORDINATES.md`

Run:

```powershell
python .\tools\phase17_refresh_venue_coordinates.py --write
python .\tools\phase17_patch_openmeteo_coordinate_loader.py --write
python -m pytest tests/test_phase17_venue_coordinates.py -q
```
