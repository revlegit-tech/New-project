# Phase 12 — Advanced Prop Detail Parity

This overlay restores the premium advanced prop detail experience in the runtime-isolated Outlier UI.

## Apply

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\phase12_advanced_prop_detail_parity_artifacts.zip" -DestinationPath . -Force
$env:PYTHONPATH = (Get-Location).Path
python tools/lint_frontend_safety.py --root .
python -m py_compile mlb_app/services/prop_detail_service.py
python -m pytest tests/test_phase12_advanced_prop_detail.py -q
```

## Run

```powershell
$Date = "2026-05-07"
python .\tools\run_daily_slate_pipeline.py --date $Date --season 2026 --limit 500 --source-mode canonical --skip-fetch
python -m mlb_app.server 8765 --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:8765/?view=outlier
```

Click any prop row. The detail modal should show hit-rate cards, recent-game graph, sportsbook ladder, model context, and explicit missing-data warnings.
