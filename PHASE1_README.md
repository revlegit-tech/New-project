# Phase 1 — Endpoint Parity and Legacy Triage Artifacts

This bundle executes the roadmap's Phase 1 inventory deliverable for the uploaded project snapshot.

## Files

- `docs/endpoint-triage/endpoint_triage_inventory.csv` — canonical editable triage table.
- `docs/endpoint-triage/ENDPOINT_TRIAGE_INVENTORY.md` — Markdown view of the same inventory.
- `docs/endpoint-triage/PHASE1_ENDPOINT_TRIAGE_SUMMARY.md` — executive summary and gates.
- `docs/endpoint-triage/endpoint_triage_summary.json` — machine-readable counts.
- `docs/endpoint-triage/port_queue.csv` — endpoints to port or keep in mlb_app.
- `docs/endpoint-triage/replace_queue.csv` — endpoints needing redesigned contracts/services.
- `docs/endpoint-triage/quarantine_queue.csv` — admin/training/sync/workflow endpoints to move out of public product API.
- `docs/endpoint-triage/retire_queue.csv` — likely legacy endpoints to remove after caller confirmation.
- `tools/generate_endpoint_triage.py` — dependency-free regeneration script for CI/local reviews.

## Regenerate

```bash
python tools/generate_endpoint_triage.py --root . --out docs/endpoint-triage
```

## Phase 1 gates

- No `app.py` endpoint is left without a classification.
- Mutation/workflow endpoints are explicitly marked sensitive.
- Existing `mlb_app` ports are marked `PORTED_IN_MLB_APP` but still need contract tests before removing legacy branches.
- Quarantine rows should not be exposed through normal bettor-facing runtime until middleware/auth/rate-limit boundaries exist.
