# Phase 6 — Mutation Endpoint Security

This cumulative overlay adds the Phase 6 mutation boundary for `mlb_app`.

## What changed

- Route metadata can now mark endpoints as `mutation=True`.
- Product mutations are enforced centrally in `Router.dispatch()`.
- `X-Baseball-Prop-Action: 1` remains a required intent signal.
- Local mode also requires loopback client IP.
- Staging/production require a configured mutation token.
- Production can require CSRF via `MLB_CSRF_TOKEN` or `MLB_REQUIRE_CSRF=1`.
- A process-local token bucket returns `429` with `Retry-After` after rapid mutation calls.
- Mutation denials are logged with request ID and mutation metadata.
- Legacy mutation/workflow endpoint inventory is generated under `docs/security/`.

## Validation

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  tests/test_mutation_security.py \
  tests/test_api_contracts.py \
  tests/test_request_observability.py \
  tests/test_wsgi_smoke.py \
  tests/test_cache_store.py \
  tests/test_csv_store.py \
  -q
```

## Current protected product mutations

- `POST /api/my-picks`
- `POST /api/my-picks/update`
- `POST /api/bankroll/settings`
