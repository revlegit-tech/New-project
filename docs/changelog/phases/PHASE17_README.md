# Phase 17 — Game Context, Totals, Weather, and Park Feature Enrichment

This overlay adds Phase 17 tooling for live game-context enrichment.

## Validate

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
python -m py_compile tools/phase17_common.py tools/phase17_enrich_game_context.py tools/phase17_game_context_audit.py tools/run_phase17_game_context.py
python -m pytest tests/test_phase17_game_context.py -q
```

## Run

```powershell
$Date = "2026-05-07"
python .\tools\run_phase17_game_context.py --date $Date --season 2026 --markets batter_hits batter_total_bases
python .\tools\phase17_game_context_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
python .\tools\validate_model_readiness.py --json
```

## Commit

```powershell
git status
git add -A
git commit -m "Add Phase 17 game context enrichment workflow"
git push origin main
```
