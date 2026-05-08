# Data Health Dashboard + Workflow State Machine

This stage adds a bettor-facing `/api/data-health/dashboard` endpoint and a premium UI surface for data confidence.

## Goal

The dashboard translates raw operational checks into product-grade status cards. Normal users see whether today’s board is usable; developers can still reach repair/pipeline controls through Advanced Mode.

## Endpoint

```text
GET /api/data-health/dashboard?season=2026&date=YYYY-MM-DD
```

Top-level response fields:

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

Allowed card/phase statuses:

```text
Good
Partial
Stale
Missing
Failed
```

## Data confidence cards

The dashboard currently emits cards for:

```text
odds_freshness
playerboard_freshness
schedule_coverage
prop_coverage
weather_coverage
pitcher_coverage
lineup_coverage
bvp_coverage
savant_coverage
grading_status
model_artifacts
workflow_summaries
```

Each card includes a short summary, a metric, warnings, and an Advanced Mode repair target where applicable.

## Workflow phases

The endpoint exposes the daily workflow state machine:

```text
Morning / Pre-slate
Pre-lock
Postgame
Weekly
```

Each phase includes its checks, pass count, last run date, warnings, and errors. This gives the UI a single place to show whether the board is fresh, complete, graded, and model-ready.

## Frontend

`public/data-health-dashboard.js` renders the product-grade dashboard inside the Data Health tab. Legacy raw JSON panels remain available but are marked as Advanced Mode content.

## Design principle

The normal product surface should answer: “Can I trust today’s board?” Repair tools should remain available, but they should not be the default bettor experience.
