# Phase 18 v2 — Playerboard Context API Contract

This hotfix extends the saved Playerboard schema and saved-card loader so game-context fields survive the path:

`data/playerboard/playerboard_2026.csv -> load_saved_playerboard -> PlayerboardService -> EdgeBoardService -> /api/edge-board -> Outlier UI`.

It does not fabricate values. It only preserves fields that Phase 17/18 already populated from PropLine, Open-Meteo, OddsPapi, and local reference data.

## Fields preserved

- team_moneyline
- opponent_moneyline
- game_total
- moneyline_implied_probability
- team_implied_runs
- opponent_implied_runs
- opponent_implied_runs_proxy
- park_factor
- weather_temperature_f
- weather_wind_mph
- weather_wind_direction
- weather_humidity
- weather_precip_probability
- roof_status
- venue
- game_context_source

Opening-line movement fields remain missing unless a provider snapshot supplies them.
