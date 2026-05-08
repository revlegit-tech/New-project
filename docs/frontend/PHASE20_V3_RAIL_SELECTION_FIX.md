# Phase 20 v3 — Rail Selection and Modal Layout Fix

This hotfix keeps the right rail populated after clicking a prop and after the advanced modal opens.

## Fixes

- Rewrites `public/outlier-detail.js` with a durable `openRow(row, index)` API.
- Patches `public/outlier-board.js` so row clicks update the right rail before and after opening the advanced modal.
- Adds CSS to reduce unused modal space and balance the advanced detail layout.
- Keeps Phase 18/19 game context display in the rail: moneyline, totals, implied runs, weather, roof, and movement.

## Apply

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\phase20_v3_rail_selection_fix.zip" -DestinationPath . -Force
$env:PYTHONPATH = (Get-Location).Path
python .\tools\apply_phase20_v3_rail_selection_fix.py
python -m py_compile tools/apply_phase20_v3_rail_selection_fix.py
python tools/lint_frontend_safety.py --root .
```

Restart the app and hard-refresh the browser.
