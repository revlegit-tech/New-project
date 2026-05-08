# Phase 20 — UI Polish + Audit Cleanup

Phase 20 improves the readability of the Game Context rail and reduces non-actionable audit noise.

## UI changes

The right rail Game Context card now formats:

- Team/Opponent moneyline as American odds
- Game total as a clean number
- Moneyline implied probability as a true probability percentage
- Team/opponent implied runs to two decimals
- Weather as temperature, wind speed/direction, humidity, and precipitation
- Roof status as human-readable text
- Open line and movement fields as pending until a second snapshot or provider source exists

## Audit changes

Phase 20 distinguishes:

- Required numeric live fields
- Required string live fields such as `best_book`, `venue`, `roof_status`, and `weather_wind_direction`
- Advisory/movement fields such as `open_team_moneyline`, `moneyline_move`, `open_game_total`, and `total_move`
- Blocked leakage fields, which are reported as notes instead of noisy warnings

Opening-line movement remains advisory until Phase 19 has two observed snapshots or OddsPapi/opening-line data is configured.

## Commands

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"

Expand-Archive "$env:USERPROFILE\Downloads\phase20_ui_polish_audit_cleanup_artifacts.zip" -DestinationPath . -Force

$env:PYTHONPATH = (Get-Location).Path
python .\tools\apply_phase20_ui_and_audit_polish.py
python -m py_compile tools/apply_phase20_ui_and_audit_polish.py tools/phase20_audit_cleanup_qa.py tools/phase16_common.py tools/phase16_live_feature_audit.py tools/phase17_game_context_audit.py
python -m pytest tests/test_phase20_ui_and_audit_polish.py -q

$Date = "2026-05-07"
python .\tools\phase20_audit_cleanup_qa.py --date $Date --market batter_hits
```
