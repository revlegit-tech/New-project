# Sprint 7 Production Security Posture

The production runtime remains the ASGI path:

```text
mlb_app.asgi:app -> create_app -> AppContainer -> services -> repositories
```

## Gunicorn + Uvicorn production command

```bash
gunicorn --config config/gunicorn.asgi.conf.py -k uvicorn.workers.UvicornWorker mlb_app.asgi:app
```

`make serve` wraps the same command. `make serve-wsgi-legacy` is compatibility-only and must not receive production traffic.

## Required environment controls

| Variable | Default | Production target | Purpose |
|---|---:|---:|---|
| `MLB_CSP_REPORT_ONLY` | `1` | `0` | Switch from report-only CSP to enforced CSP. |
| `MLB_CSP_ALLOW_INLINE` | `0` | `0` | Keep inline script/style disabled for the Outlier UI bundle. |
| `MLB_READ_RATE_LIMIT_PER_MINUTE` | `120` | traffic-dependent | Refill rate for expensive read endpoints. |
| `MLB_READ_RATE_LIMIT_BURST` | `30` | traffic-dependent | Per-client burst capacity for read endpoints. |
| `MLB_ADMIN_RATE_LIMIT_PER_MINUTE` | `10` | low | Admin endpoint limit. |
| `MLB_TRUSTED_PROXY_CIDRS` | `127.0.0.1/32,::1/128` | proxy CIDRs only | Only these direct peers may supply `X-Forwarded-For` / `X-Real-IP`. |

## Read endpoints protected by Sprint 7

- `GET /api/app/status`
- `GET /api/edge-board`
- `GET /api/playerboard`
- `GET /api/playerboard/health`
- `GET /api/prop-detail`
- `GET /api/model-cards`
- `GET /api/model-card`
- `GET /api/model-cards/{market}`
- all `/api/admin/*` methods through the admin limiter

Rate-limit denials return a standardized envelope with `status`, `code`, `message`, `requestId`, and `meta`, plus a `Retry-After` header.

## Trusted proxy behavior

Forwarded headers are ignored unless the direct client IP is inside `MLB_TRUSTED_PROXY_CIDRS`. Access logs now include:

- `client_ip`: the effective client IP used for rate limiting and audit trails.
- `directClientIp`: the direct peer connected to the ASGI worker.
- `effectiveClientIp`: the trusted forwarded IP, or direct peer when no trusted proxy is present.
