# Production Hosting

Production should run separate roles:

- `web`: FastAPI only, serving `mlb_app.asgi:app`.
- `worker`: ad hoc or queued workflow execution.
- `scheduler`: timed workflows such as live snapshots.
- `postgres`: warehouse/state database.
- artifact storage: external persistent storage for generated snapshots, status, and model artifacts.

`Dockerfile` starts only the web runtime. `docker-compose.example.yml` shows placeholders for web, worker, scheduler, and PostgreSQL. Replace all placeholder passwords and URLs before deployment.

Do not bake generated `data/`, `models/`, local status files, or secrets into the image. Mount or sync generated artifacts separately.

Safe public status endpoints:

- `GET /api/health`
- `GET /api/runtime/status`
- `GET /api/workflow/status`
- `GET /api/data-freshness`
