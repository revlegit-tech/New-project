# Trust Surface + First Route Migration

This slice introduces the first bettor-facing trust layer while preserving legacy endpoint URLs.

## Product state

The default product state is `research_mode`. In this state the UI should use safe decision language:

- `No bet`
- `Watchlist`
- `Model lean`

Do not show confident pick language until a market has an exact model artifact, sufficient training data, calibration status, and a latest fully graded slate.

## New/updated API fields

`GET /api/app/status` now includes:

- `productState`
- `productStateDetail`
- `latestBoardDate`
- `latestFullyGradedDate`
- `dataConfidence`
- `grading.state`
- `productionEligibleMarkets`

`GET /api/playerboard/health` now includes:

- `productState`
- `grading`
- `latestFullyGradedDate`
- `dataConfidence`
- `slateStatus`
- `modelReadiness`
- `trust`

## Migrated modular routes

The modular server now owns these read-only routes:

- `/api/app/status`
- `/api/playerboard/health`
- `/api/playerboard`
- `/api/data-health`
- `/api/grading/health`
- `/api/prop-ml/status`

The legacy `app.py` wrappers delegate to the same services where practical, so existing endpoint URLs remain stable during migration.

## Grading states

Supported states:

- `not_started`
- `waiting_for_finals`
- `boxscores_loaded`
- `grading_running`
- `graded`
- `partial`
- `failed`

The UI should display today's board date separately from `latestFullyGradedDate`.
