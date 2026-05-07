# Baseball Prop Predictor Premium Integration Patch

Patched against `Baseball_Prop_Predictor_Full_Audit.txt` on 2026-05-06.

## Implemented

### Critical data joins
- Added TEAM_NORM to `player_hit_rates.py` and frontend `public/outlier-ui.js`.
- Normalized legacy/team aliases in `baseball_ui_tools.py` for game context, lineup, weather, and odds wiring.

### Props table
- Removed recommendation text from proposition cells.
- Removed pitcher sub-line from player cells.
- Added IP% label and implied-probability tooltip.
- Added background line-shopping fetches against `/api/stage3/line-comparison` and sportsbook chips for top board rows when data exists.

### Prop detail charts and UX
- Made miss bars visible with translucent white.
- Made supporting stat bars visible.
- Added canvas draw error boundaries.
- Added AbortController request cancellation for prop card, logs, game context, and lineup fetches.
- Added the 4th detail fetch for `/api/game/lineup`.
- Improved BvP fallback copy.
- Collapsed pitch-mix segments under 3% into `Other`.

### Right rail
- Added detail rail rendering for Starting Pitchers, Bullpen Stats, Batter Stats, and Ballpark.
- Added pitcher season stats to `team_side_payload()`.
- Added circular team badges, stat color rules, selected batter row highlight, bullpen no-data state, and stadium indoor/outdoor logic.

### Games view data wiring
- Expanded `game_context_payload()` market loader to read Oddspapi game market CSVs, `data/imports/game_odds_template_*.csv`, and game-market rows from odds snapshots when present.
- Added date/team fallback grouping so rows without fixture IDs do not collapse every slate into one game.
- Added weather field normalization for `temperatureF`, `windMph`, `windDirection`, and roof status.

### Insights
- Reworked `insights_feed_payload()` to generate mixed streak, H2H, split/recent-form, steam, and team-form cards using the audit scoring model.
- Replaced raw prop-card stat dump insights with more narrative copy.

### Navigation and responsive polish
- Replaced checkbox-looking nav icon styling with premium icon glyphs.
- Added page fade-in-up transition.
- Added responsive caps/breakpoints for 1920, 1279, 1023, and 639 widths.
- Added `defer` to `outlier-ui.js`.

## Verification run

```bash
node --check public/outlier-ui.js
python -m py_compile player_hit_rates.py baseball_ui_tools.py stage3_betting_features.py unified_prop_card.py unified_prop_context.py app.py
python -m compileall -q .
```

Targeted payload smoke tests completed for hit-rates, game context, lineup, and insights feed.

## Data still required for full visual completion

The code now wires the data paths, but these local cache files are still sparse or absent in the provided archive:

- Game odds: no usable game-market odds rows were present for the tested slates, so Games can still show `--` until `data/imports/game_odds_template_YYYY-MM-DD.csv` is filled or Oddspapi game-market CSVs are generated.
- Savant pitch mix / zones: the Savant cache needs to be populated for Pitch Arsenal and Heatmaps to render real visuals.
- BvP career rows: `batter_vs_pitcher_pa_2026.csv` remains effectively empty, so the improved fallback copy will show until this workflow is populated.
- Weather: weather cache remains sparse; Stadium card now renders venue/indoor/outdoor fallbacks and will show temperature/wind when rows exist.
