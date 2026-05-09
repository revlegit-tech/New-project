# Sprint 5 — Outlier UI Productionization

Sprint 5 makes the Outlier board the production frontend while preserving the historical operations UI at `/legacy.html`.

## What changed

- Added a Vite project under `frontend/` with separate `index.html` and `legacy.html` entrypoints.
- Added `frontend/src/outlier/main.ts` as the production Outlier boot path.
- Added shared market definitions in `frontend/src/shared/markets/markets.ts`.
- Added shared design tokens and layout CSS in `frontend/src/shared/styles/`.
- Generated fingerprinted static assets under `public/assets/` and made `/` load only those Outlier assets.
- Moved the old tool shell to `/legacy.html`, where it loads the legacy script stack explicitly.
- Gated non-MLB sports as disabled "Coming soon" navigation items.
- Added a board trust surface for collector, playerboard, odds, model readiness, and schema version.
- Added E2E coverage for board loading, filtering, detail rail, pick save, exposure refresh, and stale warnings.

## Local commands

```bash
npm install
npm run dev
npm run build
npm run test:e2e
```

The backend dev server still runs separately with:

```bash
python -m mlb_app.server 8765
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8765`.

## Production serving rule

`public/index.html` is now the built Outlier artifact. It should not contain legacy DOM, legacy script loaders, URL-param UI switching, or static non-hashed Outlier assets. The legacy operations interface is intentionally isolated at `public/legacy.html`.
