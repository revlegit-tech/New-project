# Phase 17 — Game Context, Totals, Weather, and Park Feature Enrichment

Phase 17 enriches live Playerboard rows with same-date game context required by the model/trust surface:

- team and opponent moneylines
- game total and line movement fields
- moneyline-implied probability
- team/opponent implied-run proxy derived from real moneyline + total inputs
- park factor
- weather context
- context source provenance

The scripts do not fabricate context. Missing upstream schedule, weather, park, or game-line data remains visible as audit warnings.

## Run

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python .\tools\run_phase17_game_context.py --date $Date --season 2026 --markets batter_hits batter_total_bases
python .\tools\phase17_game_context_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
```

## Source discovery

The enrichment tool looks for local same-date CSV/JSON files under `data/` and `data/warehouse/`, including common paths such as:

```text
data/warehouse/summaries/daily_summary_YYYY-MM-DD.json
data/warehouse/schedule/mlb_schedule_YYYY-MM-DD.csv
data/warehouse/weather/weather_YYYY-MM-DD.csv
data/warehouse/odds_snapshots/game_lines_YYYY-MM-DD.csv
data/warehouse/odds_snapshots/odds_movement_YYYY-MM-DD.csv
data/odds/game_lines_YYYY-MM-DD.csv
```

It intentionally skips Playerboard, training, model, cache, and PropLine prop files while scanning for game context.

## Trust rules

- `team_implied_runs` and `opponent_implied_runs` are written only when both moneylines and a game total exist.
- The implied-runs fields are marked with `implied_runs_source=moneyline_total_proxy`.
- Weather and park fields are only written when a source file supplies them.
- `actual`, `target`, and other settled-result fields remain blocked from live model inputs.

## Output files

```text
data/models/audits/phase17_game_context_enrichment_<season>_<date>.json
data/models/audits/phase17_game_context_audit_<season>_<date>.json
```
