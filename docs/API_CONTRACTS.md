# API Contracts

The product is moving toward explicit contracts so the UI can trust response shapes while backend routes are migrated out of `app.py`.

## Stable response conventions

All JSON API responses should use:

- `status`: `ok`, `partial`, `not_ready`, or `error`.
- `code`: machine-readable error code for failures.
- `error`: safe user-facing error message for failures.
- Domain-specific payload fields with stable names.

Internal tracebacks, file paths, and secret-bearing configuration values must not be returned to clients.

## Current modular route contracts

### `GET /api/app/status`

Required fields:

- `status`
- `productState`
- `generatedAt`
- `researchMode`
- `modelPolicy`
- `trainedMarkets`
- `productionEligibleMarkets`

The default product state remains `research_mode` until market-specific readiness, grading, and calibration gates are passed.

### `GET /api/prop-ml/status`

Required fields:

- `status`
- `policy`
- `markets`
- `trainedMarkets`
- `readyMarkets`
- `productionEligibleMarkets`

Each market object should make readiness explicit instead of silently falling back to a generic model.

## Testing

Contract tests live in `tests/test_api_contracts.py` and should be extended whenever a route is moved into `mlb_app/routes/`.

## Trust status fields

Read-only bettor-facing endpoints should expose trust status without changing their URL:

- `productState`: string state, usually `research_mode`.
- `productStateDetail`: label, message, severity, and allowed decision labels.
- `latestFullyGradedDate`: most recent slate that is fully graded.
- `dataConfidence`: `Good`, `Partial`, or `Missing`.
- `grading.state`: one of the grading state-machine values.
- `modelReadiness`: market-level readiness gates.

These fields are additive and should not remove legacy response fields.


## `GET /api/prop-detail`

Returns the bettor-facing drilldown contract for one Edge Board row. The response includes `overview`, `priceComparison`, `modelExplanation`, `playerContext`, `gameContext`, `riskContext`, and `tracking`. It is read-only and does not alter user picks or model backtests.


## `GET /api/data-health/dashboard`

Product-grade data confidence dashboard. Returns normalized cards for odds freshness, playerboard freshness, schedule coverage, prop coverage, weather, pitcher coverage, lineup coverage, BvP, Savant, grading status, model artifacts, and workflow summaries.

Required fields:

```text
status
ok
version
overallStatus
dataConfidence
productState
latestBoardDate
latestFullyGradedDate
summary
cards
workflowPhases
warnings
advancedLinks
raw
```

Card and workflow phase statuses must be one of `Good`, `Partial`, `Stale`, `Missing`, or `Failed`.

## `GET /api/workflows/health`

Read-only workflow summary endpoint for the modular server. Returns latest daily health, daily grading, and weekly repair summary metadata.
