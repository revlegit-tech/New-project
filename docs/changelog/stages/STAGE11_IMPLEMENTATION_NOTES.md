# Stage 11 Implementation Notes

## Scope
Final polish pass for the MLB Outlier-style interface:

- Completed left navigation behavior and active styling.
- Added MLB-only sport tab behavior with toast feedback for non-MLB sports.
- Added right-rail drawer behavior at tablet widths with overlay dismissal.
- Added bottom navigation at small widths.
- Tightened mobile/tablet breakpoints so mobile cards only take over on narrow screens.
- Added right-rail skeleton blocks while the board is loading.
- Wired right-rail tabs for Matchup, Injuries, and Insights instead of leaving the tab strip as static UI.
- Wrapped frontend fetches through retry-aware `getJson()` with exponential backoff.

## Files Changed

- `public/outlier-ui.js`
- `public/outlier-ui.css`
- `STAGE11_IMPLEMENTATION_NOTES.md`

## Validation

Executed:

```bash
node --check public/outlier-ui.js
python -m py_compile app.py stage3_betting_features.py baseball_ui_tools.py player_hit_rates.py
```

Both checks passed.

## QA Notes

- At widths above 1440px, the three-column layout remains visible.
- At 1440px and below, the right rail uses the narrower 280px width.
- At 1280px and below, the right rail becomes a slide-in drawer triggered by the `i` button in the filter bar.
- Below 1024px, the sidebar becomes a bottom nav bar and the main column takes the full width.
- Below 640px, the props table swaps to mobile cards.
- Toasts continue to stack in the bottom-right, and on mobile they lift above the bottom nav.
