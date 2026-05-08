# Phase 12 — Advanced Prop Detail Parity

Phase 12 restores the premium prop-inspection workflow that was lost during the runtime-isolated Outlier shell migration.

## Goals

- Clicking any prop row opens a high-density advanced detail modal.
- Hit-rate windows are backend-computed, not frontend placeholders.
- Recent game bars show actual cached game-log outcomes for the selected market, line, and side.
- Sportsbook duplicates remain collapsed on the board while the modal shows the full book ladder.
- Over / Under / Yes / player-outcome identity is preserved when looking up details.
- Missing data remains explicit through the trust surface.

## UI surfaces

### Board row click

`public/outlier-board.js` now forwards the row's `season`, `marketDisplay`, and `rawLabel` into the detail lookup. That prevents an Over row and Under row for the same player/market/line from being confused.

### Right rail

`public/outlier-detail.js` now shows:

- model / implied / edge / odds / book count
- mini L5/L10/L20 strip
- matchup tab
- Trends tab with hit-rate bars and recent game graph
- sportsbook ladder card
- trust-surface missing-data card

### Advanced modal

`public/prop-detail.js` now renders:

- premium hero with key metrics
- hit-rate profile cards for L5/L10/L20/H2H/season/previous season
- recent game graph and recent game table
- sportsbook ladder with best price highlighted
- player/game context
- model explanation
- risk and trust context

## Backend contract

`mlb_app/services/prop_detail_service.py` now includes the selected side in detail payloads and uses `rawLabel` to avoid selecting the wrong row when multiple sides exist.

`trendProfile` includes:

```json
{
  "windows": {},
  "recentGames": [],
  "sourceStatus": "ok | missing_game_logs | error",
  "line": "0.5",
  "direction": "over | under",
  "rawLabel": "Over",
  "statKey": "hits"
}
```

## Validation

```powershell
python tools/lint_frontend_safety.py --root .
python -m py_compile mlb_app/services/prop_detail_service.py
python -m pytest tests/test_phase12_advanced_prop_detail.py -q
```
