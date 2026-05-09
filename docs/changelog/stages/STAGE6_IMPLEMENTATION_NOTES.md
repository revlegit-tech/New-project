# Stage 6 Implementation Notes

Implemented against `UPDATED_INTEGRATION_ROADMAP(3).txt` with focus on the MLB player prop detail page.

## Frontend

Modified `public/outlier-ui.js` and `public/outlier-ui.css`:

- Added row-click navigation from Props table to `PropDetail`.
- Added detail header with back navigation, matchup/time text, team-colored avatar, player identity, and proposition title.
- Added Under/Over line selector with alt-lines dropdown and implied probability display.
- Added 13 stat tabs: TB, H, H+R+RBI, HR, RBI, R, SB, 1B, 2B, 3B, BB, SO, FS (UD).
- Added period filters: L5, L10, L20, H2H, 2026, 2025.
- Added bar/table chart toggle.
- Added performance summary line with current period, secondary hit-rate windows, average, and median.
- Added Canvas 2D primary bar chart with dashed threshold line, green hit bars, gray miss bars, x-axis labels, and hover tooltip.
- Added supporting stats mini charts for plate appearances, hits, and extra-base hits.
- Added insight block wired to `/api/unified-prop-card/predict` response insights.
- Added matchup stats block using available cached contexts and graceful fallback when BvP splits are missing.
- Added pitch arsenal card with Canvas donut when `savant.pitcher.pitchMix` exists and fallback text when absent.
- Added heatmap card with 4x4 Canvas zone maps when `savant.pitcher.zoneFrequency` / `savant.batter.zonePerformance` exist and fallback text when absent.
- Added skeleton cards and inline error panels for independently-loaded detail sections.

## Backend compatibility

Modified `app.py`:

- Added POST support for `/api/unified-prop-card/predict` so Stage 6 can use the roadmap’s POST flow while preserving the existing GET fallback.
- Enriched `/api/incremental-stats/lookup` so requests with `player=...` return `gameLogs` from cached incremental CSVs. This lets the detail charts use real game-log data instead of only search metadata.

## Validation performed

- `node --check public/outlier-ui.js`
- `python -m py_compile app.py baseball_ui_tools.py player_hit_rates.py unified_prop_card.py`
- Stage 10.4 hit-rate stress test: `rowsLoaded: 384`
- Detail logs smoke test for Josh Bell returned 33 cached game logs.
- `/api/game-context` smoke test for MIN on 2026-05-06 returned a game with bullpen arrays on both sides.
- `/api/game/lineup` smoke test returned the documented `estimated_by_pa` fallback because projected lineups were not present in summary JSON.

## Known graceful fallbacks

- The current Savant response exposes the expected field audit paths, but the local cache did not contain pitch mix or zone grids for the Josh Bell / Miles Mikolas smoke test. The UI now renders the required fallback messages instead of crashing.
- Matchup/BvP split data is shown when available; otherwise the UI displays cached season context tables.
