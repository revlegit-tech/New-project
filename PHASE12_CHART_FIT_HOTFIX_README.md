# Phase 12 Chart Fit Hotfix

This overlay fixes the advanced prop detail recent-game graph overflowing horizontally inside the modal.

Apply with:

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\phase12_chart_fit_hotfix.zip" -DestinationPath . -Force
$env:PYTHONPATH = (Get-Location).Path
python tools/lint_frontend_safety.py --root .
```
