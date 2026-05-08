# Phase 11 — Daily Slate Pipeline

This phase adds a repeatable slate refresh runner and validator on top of the retired `app.py` production tree.

## Added

- `tools/run_daily_slate_pipeline.py` — orchestrates schedule, weather, odds movement, PropLine fetch, Playerboard rebuild, optional stats catchup, optional grading, data-health, and validation.
- `tools/validate_daily_slate.py` — validates canonical PropLine rows, Playerboard rows, duplicate groups, merged books, hit rates, and recent-game payloads.
- `docs/data/PHASE11_DAILY_SLATE_PIPELINE.md` — daily operating guide.
- `tests/test_phase11_daily_slate_pipeline.py` — static/unit coverage for parser, validation behavior, dry-run behavior, and JSON output shape.

## Standard command

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"
python .\tools\run_daily_slate_pipeline.py --date $Date --season 2026 --limit 500 --source-mode canonical
```

## Open

```text
http://127.0.0.1:8765/?view=outlier
```
