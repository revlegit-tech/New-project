# Outlier Prop Clickthrough Restore

This hotfix restores the old interaction model: selecting a prop row opens the advanced Prop Detail modal while also updating the Outlier right rail.

## Behavior

- Click any board row to open advanced prop statistics.
- Press Enter or Space while focused on a row to open the same detail.
- The right rail continues to show quick Matchup / Trends / Model context.
- The modal uses the existing `/api/prop-detail` contract and remains separate from legacy `app.py`.

## Why this patch is small

The advanced detail UI already existed in `public/prop-detail.js`. The regression came from the runtime-isolated Outlier shell not loading or invoking that module. This patch lazy-loads it only when a user selects a prop row.
