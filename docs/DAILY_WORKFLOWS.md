# Daily Workflows

The app should expose one source of truth for slate state: what has been fetched, what is fresh, what is graded, and which markets are model-ready.

## Morning / pre-slate

1. Fetch schedule.
2. Fetch odds and props.
3. Fetch weather and probable pitchers.
4. Build the playerboard.
5. Run data contract checks.
6. Publish the board as research-ready only if freshness and coverage are acceptable.

## Pre-lock

1. Refresh odds.
2. Detect line movement.
3. Update best available prices.
4. Re-score market edges.
5. Flag stale or incomplete markets.

## Postgame

1. Fetch finals and boxscores.
2. Grade playerboard rows and user picks.
3. Update model/backtest summaries.
4. Save a daily health report.

## Weekly

1. Run repair jobs.
2. Retrain eligible markets with chronological validation.
3. Recalibrate probabilities.
4. Generate model cards.
5. Archive cache outputs.

## CI/output policy

Scheduled workflows upload generated data as GitHub artifacts. They do not push generated data directly to `main`.
