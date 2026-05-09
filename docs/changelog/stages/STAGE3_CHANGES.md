# Stage 3 Betting Product UI Integration

This build completes the audit's Stage 3 betting-specific layer without removing the Stage 0/1/2 product UI work.

## Added

### 1. Multi-book line comparison
- New endpoint: `/api/stage3/line-comparison`
- Reads `data/cache/odds_movement/prop_snapshots_2026.csv`
- Matches the active prediction context by season/date/market/player/team/opponent/pitcher
- Shows the latest available price by sportsbook
- Calculates implied probability, model edge, EV per unit, and Kelly fraction for each book
- Highlights the best book by EV/edge

### 2. Kelly bankroll calculator
- Integrated into prediction output add-ons after a result card renders
- Supports editable bankroll with `localStorage` persistence
- Shows full Kelly, half Kelly, and quarter Kelly stake sizes
- Safely recommends $0 when the model has no positive Kelly stake

### 3. Steam alert feed
- New endpoint: `/api/stage3/steam-alerts`
- Reads `data/cache/odds_movement/prop_movement_2026.csv`
- Flags props with line movement of 0.5+ or odds movement of 15+ cents
- Injects a “Steam Alert Feed” into Today's Board
- Includes date/market filters and movement direction copy

### 4. Bet tracker analytics
- New endpoint: `/api/stage3/pnl-analytics`
- Reads `data/backtests/playerboard_backtest_2026.csv`
- Reads `data/audit/model_audit_2026.json`
- Injects a “Bet Tracker Analytics” panel into My Picks
- Shows units, record, win rate, ROI, current/longest streaks, market splits, a cumulative units sparkline, and model audit warnings

## Files changed

- `app.py`
  - Registers three additive Stage 3 API routes.
- `stage3_betting_features.py`
  - New backend helper module for line comparison, steam alerts, and P&L analytics.
- `public/stage3-betting-ui.js`
  - New frontend enhancement module.
- `public/index.html`
  - Loads the Stage 3 frontend module after Stage 2.
- `public/styles.css`
  - Adds Stage 3 component styles.

## Validation performed

- `python -m py_compile app.py stage3_betting_features.py`
- `node --check public/stage3-betting-ui.js`
- Started the local app and verified JSON responses from:
  - `/api/stage3/steam-alerts`
  - `/api/stage3/pnl-analytics`
  - `/api/stage3/line-comparison`

## Notes

The line-comparison UI depends on saved snapshot rows matching the exact prop context. If a prop shows “No alternate books found,” run Odds Movement Sync or confirm the active player/date/market exists in the snapshot CSV.
