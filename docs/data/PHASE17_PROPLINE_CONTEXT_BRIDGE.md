# Phase 17 v2 — PropLine Game Context Bridge

This patch changes the game-line enrichment default from The Odds API to PropLine.

## Why

The Odds API returned a 401 in local testing. PropLine is already available in this project for player props, so the Phase 17 bridge now tries PropLine game-line markets first.

## Sources

- MLB schedule / venue: MLB Stats API
- Weather: Open-Meteo using explicit venue coordinates
- Moneyline / game total: PropLine bulk game-line endpoint (`h2h,totals`)
- Park factor: explicit local reference table

## Commands

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python .\tools\run_phase17_context_from_apis.py --date $Date --season 2026 --markets batter_hits batter_total_bases --line-source propline
python .\tools\phase17_game_context_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
python .\tools\phase16_live_feature_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
```

Use `--line-source the_odds_api` only when a valid Odds API key is available. Use `--skip-odds` or `--line-source none` to avoid paid game-line calls.

## Trust behavior

This does not fabricate moneylines, totals, or implied runs. If PropLine does not return a same-date game-line match, the fields stay blank and the audits keep warnings visible.
