# Phase 18 — Provider-Backed Context Collector

Phase 18 makes the daily collector responsible for filling the remaining game-context fields that the frontend needs:

- PropLine: game lines, totals, and player props.
- OddsPapi: optional snapshots/opening/CLV archives when `ODDSPAPI_API_KEY` is configured.
- Open-Meteo: venue weather supplements, including humidity and wind direction.
- Local references: MLB venue coordinates and roof type/status notes.

## Rules

- No fabricated moneylines, totals, opening lines, or implied runs.
- Re-run Phase 17 context bridges first, then supplement missing weather fields.
- Write canonical game context files, then denormalize verified fields onto Playerboard for UI speed.
- Keep missing provider fields visible in audits.

## Commands

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python -m py_compile tools/phase18_fill_missing_context.py tools/apply_phase18_season_collector_hook.py tools/phase18_context_qa.py
python -m pytest tests/test_phase18_context_collector.py -q

python .\tools\phase18_fill_missing_context.py --date $Date --season 2026 --markets batter_hits batter_total_bases --line-source propline
python .\tools\phase18_context_qa.py --date $Date --market batter_hits
```

## Optional OddsPapi

```powershell
$env:ODDSPAPI_API_KEY = "YOUR_KEY"
$env:ODDSPAPI_MLB_TOURNAMENT_ID = "YOUR_MLB_TOURNAMENT_ID_IF_KNOWN"
python .\tools\phase18_fill_missing_context.py --date $Date --season 2026 --markets batter_hits batter_total_bases
```

The script archives OddsPapi raw snapshots to `data/warehouse/game_context/` and uses them only when a safe parser can identify the line fields. Opening-line fields remain missing if the source does not provide them.

## Hook into season_auto_collector

```powershell
python .\tools\apply_phase18_season_collector_hook.py
```

After that, normal collector snapshots will run the Phase 18 context collector after Playerboard generation.
