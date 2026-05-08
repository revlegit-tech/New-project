# Phase 17 v6 — Game Context API Contract Wiring

This hotfix wires the canonical game-context layer back into the new `mlb_app` runtime API contract.

It does **not** add features to legacy `app.py`.

## Problem

The canonical Phase 17 files and audits showed moneyline, game total, implied runs, weather, venue, and park factor were populated, but `/api/edge-board` rows still returned blanks for those fields. That meant the Outlier right rail and advanced modal rendered `Missing` even though the data existed on disk.

## Fix

- `EdgeBoardService` now joins `data/warehouse/game_context/game_context_DATE.csv` into returned board rows by `team + opponent`.
- The row includes both snake_case and camelCase aliases so existing UI code can read either style.
- `PropDetailService` now exposes the Phase 17 fields in `detail.gameContext`.
- `prop-detail.js` shows Team ML, Opp ML, Game Total, ML IP, Team Runs, Opp Runs, Park, Weather, and Pitcher in the advanced modal.

## QA

Run with the server already open:

```powershell
$Date = "2026-05-07"
$payload = Invoke-RestMethod "http://127.0.0.1:8765/api/edge-board?date=$Date&market=batter_hits&limit=5&refresh=1"
$payload.rows | Select-Object -First 5 player,team,opponent,team_moneyline,opponent_moneyline,game_total,moneyline_implied_probability,team_implied_runs,opponent_implied_runs,weather_temperature_f,weather_wind_mph | Format-List
```

Expected: those fields should no longer be blank when the Phase 17 context CSV exists.
