# `/api/app/status` Contract — app-status-v1

Phase 7 makes the trust surface contract-driven. The endpoint keeps the legacy top-level fields used by the Outlier UI, but now emits an explicit schema marker and request metadata so frontend validation can fail closed.

Required fields include `productState`, `productStateDetail`, `grading.state`, `dataConfidence`, `productionEligibleMarkets`, `latestBoardDate`, `playerboard`, `grading`, `workflows`, and `meta.schema`.

`public/trust-surface.js` validates the response before rendering. If required fields are missing or malformed, it logs a contract warning and renders a conservative **Research Only** state. API-sourced strings continue to render only through `textContent` and DOM construction.

The UI must not infer readiness from missing values. Missing models, stale board data, delayed grading, and malformed payloads are all explicit trust states.

The backend validator is `mlb_app.schemas.app_status.validate_app_status_payload()`.

Contract fixtures live in `tests/fixtures/app_status/` and cover ready, research-only, missing-model, stale-board, grading-delayed, and malformed payloads.
