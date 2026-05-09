# Sprint 8 Frontend Consolidation

The production Outlier UI source of truth is `frontend/src`. The deployed `public/index.html` should reference Vite-built fingerprinted assets under `public/assets/`, not legacy hand-authored browser scripts.

## Implemented source modules

```text
frontend/src/outlier/
  main.ts                  # production shell composition
  app/state.ts             # single board/UI state factory
  app/keyboard.ts          # keyboard research workflow
  board/virtualized.ts     # 500-row interactive board window
  trust/index.ts           # row freshness/readiness helpers
  detail-rail/index.ts     # detail rail module boundary
  model-room/index.ts      # model room module boundary
  picks/index.ts           # picks module boundary
```

## Product behavior covered

- Sticky board header and sticky first column for research sessions.
- Keyboard navigation: arrow keys move rows, `Enter` opens the rail, `Escape` closes it, `/` focuses search.
- Board rows expose readiness and freshness without opening the detail rail.
- The board renders a 500-row interactive window and reports when additional filtered rows exist.
- Legacy scripts remain isolated to `legacy.html`; production `index.html` is Vite-only.

## Validation

Run:

```bash
python -m pytest tests/test_sprint5_frontend_build.py tests/test_phase8_frontend_architecture.py
npm run build
```

`npm run build` requires local Node dependencies (`npm ci`) before execution.
