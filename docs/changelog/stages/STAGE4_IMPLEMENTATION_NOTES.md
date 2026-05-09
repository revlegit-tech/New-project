# Stage 4 Implementation Notes

Integrated Stage 4 UX/performance additions on top of the existing Stage 3 fixes.

## Completed

- Added a sticky Active Bet context strip below the page navigation.
  - Shows Player, Market, Date, Line, and Odds.
  - Updates from the shared active-bet context in real time.
  - Clicking a field scrolls/focuses the corresponding primary input.

- Improved Kelly calculator rendering.
  - Initial render builds the full panel once.
  - Bankroll edits now update only the stake values and notes.
  - Preserves cursor/focus during typing and avoids full HTML flashes.

- Changed P&L Analytics to load on demand.
  - My Picks now shows a Load Analytics card instead of auto-fetching on every visit.
  - Results are cached in sessionStorage for one hour by season and market.
  - Changing season/market refreshes only after analytics have been loaded once.

- Made Steam Alert Feed secondary/collapsible.
  - Today's Board now shows Line Movement Alerts as a collapsed details section.
  - Alerts load only when opened or refreshed.

- Added result-card integration to remaining predictors.
  - `propml.js` now renders BaseballResultCards output.
  - `moneyline.js` now renders BaseballResultCards output.

- Confirmed previously requested Stage 3 fixes were already present.
  - Result-card edge threshold supports strong/positive/negative/neutral.
  - Strong recommendation badge has distinct visual treatment.
  - Steam tone uses explicit direction equality and weighted scoring.
  - Single-book line-shopping note is present.

## Validation

- `node --check public/*.js`: passed.
- `python -m py_compile stage3_betting_features.py app.py`: passed.
- `PYTHONPATH=. pytest -q`: 42 passed.

Note: running `pytest -q` without `PYTHONPATH=.` failed because the test runner could not import the local `app` module from the project root. With the project root on `PYTHONPATH`, the suite passed.
