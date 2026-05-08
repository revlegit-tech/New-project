# Phase 17 API Context Bridge

This overlay lets the production `mlb_app` slate pipeline pull same-date game context from APIs instead of waiting for manually prepared local files.

## Sources

| Context | Source | Key required | Behavior |
|---|---|---:|---|
| Schedule / venue | MLB Stats API | No | Writes `data/warehouse/game_context/mlb_schedule_<date>.json` and enriches game/venue fields. |
| Weather | Open-Meteo | No | Uses venue coordinates from MLB Stats API. Writes `weather_<date>.json`. |
| Game lines | The Odds API | Yes, `THE_ODDS_API_KEY` or `ODDS_API_KEY` | Populates moneyline/game-total fields only when the key and same-date odds are available. |
| Park factor | Local explicit reference | No | Writes `data/reference/park_factors.csv`; unknown venues remain blank. |

## Daily command

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python .\tools\run_phase17_context_from_apis.py --date $Date --season 2026 --markets batter_hits batter_total_bases
```

If you do not have an odds key yet, schedule/weather/park can still run:

```powershell
python .\tools\run_phase17_context_from_apis.py --date $Date --season 2026 --markets batter_hits batter_total_bases --skip-odds
```

## Optional game-line key

Do not commit API keys. Set it in your current PowerShell session:

```powershell
$env:THE_ODDS_API_KEY = "paste-key-here"
```

Or keep it in an untracked `.env` file:

```text
THE_ODDS_API_KEY=...
```

## Trust-surface rule

The script does **not** fabricate missing values. If schedule, odds, weather, or venue data cannot be matched, the related fields remain blank and the audit reports warnings.
