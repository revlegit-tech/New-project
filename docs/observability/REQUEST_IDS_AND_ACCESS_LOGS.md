# Request IDs and Structured Access Logs

Phase 3 adds request correlation at the routing boundary without changing external JSON response contracts.

## Response behavior

Every API and static response should include:

```text
X-Request-Id: <safe request id>
```

A caller may provide `X-Request-Id`; safe values are preserved for upstream correlation. Unsafe values containing control characters or unsupported characters are replaced with a generated id.

## Log behavior

Each routed request emits a single JSON stdout line:

```json
{"event":"http_request","requestId":"req-log-1234","method":"GET","path":"/api/app/status","status":200,"elapsed_ms":1.23,"client_ip":"127.0.0.1","route":"GET /api/app/status"}
```

Gunicorn captures stdout, so this gives request traceability before a fuller logging backend is introduced.

## Boundary placement

Request metadata is created before route dispatch and attached to the handler/WSGI adapter. `json_response()` adds the header centrally. `Router.dispatch()` logs route-matched requests centrally.

This preserves the route → service → repository architecture: endpoint files should not generate request IDs, hand-roll logs, or duplicate security checks.

## Next security extension point

The same `mlb_app/middleware.py` module is the extension point for Phase 6 mutation protections:

- trusted client IP extraction
- token-bucket mutation rate limits
- action endpoint auth checks
- request/job ID audit logs
