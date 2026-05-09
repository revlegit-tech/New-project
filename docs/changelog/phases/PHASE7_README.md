# Phase 7 — API Contract and Trust Surface Reliability

This cumulative overlay adds the Phase 7 trust-surface contract layer on top of Phases 0–6.

## Included

- `mlb_app/schemas/app_status.py`: canonical `app-status-v1` response builder and validator.
- `mlb_app/services/app_status_service.py`: delegates `/api/app/status` shaping to the canonical builder.
- `mlb_app/routes/health.py`: passes request ID into the app-status payload.
- `public/trust-surface.js`: validates `app-status-v1`, fails closed to `Research Only`, and keeps API strings on `textContent`.
- `tests/fixtures/app_status/*.json`: ready, research-only, missing-model, stale-board, grading-delayed, malformed.
- `tests/test_app_status_phase7_contract.py` and `tests/test_trust_surface_phase7_static_contract.py`.
- `docs/trust-surface/APP_STATUS_CONTRACT.md`.

## Validation

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  tests/test_app_status_phase7_contract.py \
  tests/test_trust_surface_phase7_static_contract.py \
  tests/test_mutation_security.py \
  tests/test_request_observability.py \
  tests/test_wsgi_smoke.py \
  tests/test_cache_store.py \
  tests/test_csv_store.py \
  tests/test_board_cache.py \
  tests/test_model_card_service.py \
  tests/test_prop_detail_service.py \
  tests/test_static_file_guard.py \
  tests/test_security_export.py \
  tests/test_trust_surface_static_safety.py \
  -q
```

Expected result: `56 passed`.
