# Phase 1 — Endpoint Parity and Legacy Triage Summary

## Inventory results

- Endpoint rows inventoried: **95**
- Unique legacy paths: **94**
- Explicit `mlb_app` routes registered: **18**
- Legacy POST-only action endpoints: **28**
- Mutation/workflow-sensitive rows: **35**
- Rows referenced by current frontend/static files: **79**

## Classification counts

| Classification | Count | Meaning |
|---|---:|---|
| PORT | 40 | Required or currently represented behavior to keep in `mlb_app` route/service/repository shape. |
| REPLACE | 22 | Required behavior likely needs redesigned contract, job semantics, or service boundary while moving. |
| QUARANTINE | 30 | Admin, training, sync, cache repair, or workflow endpoint that should not remain public product API. |
| RETIRE | 3 | Likely legacy/developer/demo route; remove after confirming no active caller. |

## Immediate Phase 1 gates

1. Treat all `QUARANTINE` rows as blocked from normal product routing until middleware/auth/rate-limit policy exists.
2. For `PORT` rows with `NOT_PORTED`, verify whether the Outlier UI still calls them before implementation.
3. For `REPLACE` rows, define schemas before copying monolith logic.
4. For `RETIRE` rows, confirm no frontend, workflow, or CI dependency remains.
5. Do not retire `app.py` until `PORT` and `REPLACE` rows are complete or formally removed.
