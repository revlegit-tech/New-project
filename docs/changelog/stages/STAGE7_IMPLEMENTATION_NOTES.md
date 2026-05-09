# Stage 7 Implementation Notes

## Completed

- Rebuilt the Outlier-style right rail with fully wired `Matchup`, `Injuries`, and `Insights` tabs.
- Added loading, empty, and error states for right-rail sections.
- Added starting pitcher cards for both teams with 2026/vs-opponent toggle support.
- Added bullpen workload table with team toggle, YTD pitch count, L3/L5 pitch counts, rest, ERA, and K%.
- Added batter stats card backed by `/api/game/lineup`, including highlighted selected-player row and lineup source label.
- Added stadium/weather card using `/api/ballpark-context` plus game-context weather fallback.
- Added right-rail async data loading for board selection and prop-detail selection.
- Added backend starter stat lines and vs-opponent stat lines to `/api/game-context`.
- Added team-code alias handling for WSH/WSN, TB/TBR, and AZ/ARI across game context and lineup lookup.
- Verified `/api/game/lineup` fallback returns top batters by AB/PA when projected lineups are unavailable.

## Validation

- `python -m py_compile baseball_ui_tools.py app.py player_hit_rates.py`
- `node --check public/outlier-ui.js`
- `python -m pytest -q` → 42 passed
- Stage 10.4 hit-rate stress test returned `rowsLoaded: 384`.

## Main Files Changed

- `public/outlier-ui.js`
- `public/outlier-ui.css`
- `baseball_ui_tools.py`
