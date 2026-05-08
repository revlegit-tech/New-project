
## Data Health Dashboard + Workflow State Machine

- Added `/api/data-health/dashboard` for product-grade data confidence cards.
- Added modular `/api/workflows/health` route.
- Added `DataHealthDashboardService` with normalized statuses: Good, Partial, Stale, Missing, Failed.
- Added workflow phase state cards for Morning / Pre-slate, Pre-lock, Postgame, and Weekly.
- Added `public/data-health-dashboard.js` to render the bettor-facing Data Health tab.
- Marked raw health output panels as Advanced Mode content.
- Added service and API contract tests for the new dashboard.

# Changelog

## My Picks + Bankroll / Exposure Controls

- Added JSON-backed My Picks storage that is separate from model backtests.
- Added conservative bankroll settings and stake caps.
- Added exposure summaries by slate, game, player, and market.
- Added pick lifecycle updates for Watching, Placed, Void, Won, Lost, Pushed, and Cashout.
- Wired Today’s Edge Board Track actions into the new My Picks flow.
- Added tests for pick storage, risk caps, API contracts, and action-header protection.

## 2026-05-07 — P2 developer experience and release hardening

### Added

- `pyproject.toml` with pytest, coverage, Ruff, and mypy configuration.
- Expanded `Makefile` commands for CI, coverage, contract tests, UI smoke tests, and data-contract validation.
- API contract tests for modular status endpoints.
- CSV data-contract validator and tests.
- Playwright smoke-test scaffolding for desktop and mobile.
- Devcontainer and Dockerfile for repeatable local setup.
- Developer, API contract, data schema, workflow, troubleshooting, legacy-script, and release-checklist docs.

### Changed

- GitHub data-generation workflows now upload generated outputs as artifacts instead of pushing directly to `main`.
- Safe export excludes test caches, type/lint caches, Node modules, coverage output, and Playwright artifacts.
- CI now runs security preflight, syntax check, lint, type check, tests with coverage, and gitleaks.

### Security

- Workflow repository permissions reduced to `contents: read` where writes are no longer required.

## Trust Surface + First Route Migration

- Added a global Research Mode trust surface to the bettor-facing homepage.
- Added product-state, grading-state, workflow-health, model-readiness, playerboard, app-status, and data-health services.
- Migrated modular routes for `/api/playerboard/health`, `/api/playerboard`, `/api/data-health`, and `/api/grading/health`.
- Updated legacy `app.py` payload wrappers to delegate to shared trust/state services while preserving endpoint URLs.
- Added latest fully graded slate, data-confidence, grading-state, and model-readiness fields to status/playerboard APIs.
- Added service and API contract tests for trust surface behavior.

## Prop Detail Page + Price/Context Drilldown

- Added `/api/prop-detail` for bettor-facing prop drilldowns.
- Added `public/prop-detail.js` modal with price comparison, model explanation, player/game context, risk context, and save-to-picks flow.
- Linked Edge Board cards to the detail view.
- Added service/API tests and documentation for the detail contract.
