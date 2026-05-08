# Phase 17 v4: Game Context Market Layer

Adds a canonical game-context layer and game-context market markers so moneyline, total, and implied-run data are not owned by batter/pitcher prop rows.

## Files

- `tools/phase17_game_context_markets.py`
- `tools/run_phase17_v4_game_context_markets.py`
- `tools/apply_phase17_v4_game_context_ui_patch.py`
- `tests/test_phase17_game_context_markets.py`
- `docs/data/PHASE17_V4_GAME_CONTEXT_MARKETS.md`

## Commands

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python .\tools\run_phase17_v4_game_context_markets.py --date $Date --season 2026 --markets batter_hits batter_total_bases --refresh-provider --line-source propline
python .\tools\apply_phase17_v4_game_context_ui_patch.py
python .\tools\phase17_game_context_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
```

The Game Context UI section will show moneyline, game total, implied runs, park, weather, and explicit missing markers.
