# Repository Instructions

This repository is an MLB-only prop research app located at:

`C:\Users\RevLe\OneDrive\Documents\New project`

The main ASGI app is `mlb_app.asgi:app`. Treat the application as a research terminal, not an auto-betting system.

## Working Rules

- Do not delete generated data.
- Do not commit large generated CSV, JSON, or model artifacts unless explicitly asked.
- Do not change `.env` or secrets.
- Keep changes small and focused.
- Prefer adding tests for every behavior change.
- Use `.\.venv\Scripts\python.exe` for Python commands on Windows.
- Use PowerShell-compatible commands in docs.
- Generated training and model outputs under `data/` should stay ignored unless source control already tracks a specific artifact.
- Do not mark any model as production eligible unless the existing governance and backtest gates pass.

## Useful Commands

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Build player prop labels:

```powershell
.\.venv\Scripts\python.exe scripts\build_player_prop_labels.py --date 2026-06-23 --season 2026 --source playerboard --format both --include-ungraded
```

Train all supported markets:

```powershell
.\.venv\Scripts\python.exe train_all_supported_markets.py --season 2026
```

Run the full MLB daily pipeline:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_mlb_full_daily_pipeline.ps1 -Date today -Season 2026 -BoardLimit 5000
```

## Current Priorities

1. Repair player prop label matching where rows are marked `missing_player`.
2. Build a consolidated verified training dataset from `data/warehouse/ml_labels` and `data/warehouse/ml_features`.
3. Train experimental market models.
4. Score the current playerboard with trained market models.
5. Join model probability and edge into the UI while keeping actionability research-only until production gates pass.
