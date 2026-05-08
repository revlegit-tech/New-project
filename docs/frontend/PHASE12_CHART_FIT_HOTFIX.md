# Phase 12 Chart Fit Hotfix

Keeps the advanced prop detail recent-game graph inside the modal viewport.

## Changes

- Restricts the recent-game graph to the latest 10 games, matching the default L10 inspection behavior.
- Changes graph layout to a contained flex row so bars compress instead of forcing a horizontal scrollbar.
- Hides unintended horizontal overflow inside the advanced detail modal while preserving vertical scrolling.

## Validation

Run:

```powershell
python tools/lint_frontend_safety.py --root .
```

Then restart the app and open `/?view=outlier`.
