# Sprint 11 — Outlier Frontend Consolidation

## Goal

Move active Outlier board and detail-rail behavior out of hand-authored `public/*.js` files and into the Vite-managed TypeScript tree under `frontend/src/outlier/`.

## Implemented module boundaries

```text
frontend/src/outlier/
  main.ts                         # composition, API loading, shell wiring only
  board/
    BoardTable.ts                  # owns table DOM and virtualized rendering window
    BoardRow.ts                    # owns row/cell rendering
    virtualized.ts                 # pure window math; no DOM dependency
    utils.ts                       # row normalization helpers shared by board/detail rail
    index.ts                       # public board module exports
  detail-rail/
    DetailRail.ts                  # isolated rail controller; fetches prop-detail itself
    index.ts                       # public rail module exports
  trust/
    index.ts                       # trust/freshness helpers shared by board and rail
```

## Board virtualization contract

`BoardTable.ts` no longer slices the first 500 rows. It accepts the full filtered row set, calculates the visible range from `scrollTop`, viewport height, fixed row height, and overscan rows, then renders only that window. Spacer rows preserve the full scroll height so the user can navigate a 500–5,000 row slate without mounting thousands of `<tr>` elements.

The pure function boundary is:

```ts
createVirtualWindow({ rowCount, scrollTop, viewportHeight, rowHeight, overscanRows })
```

That returns `startIndex`, `endIndex`, `offsetTop`, `offsetBottom`, and `totalHeight`. The DOM controller consumes this result and paints the visible rows.

## Detail rail decoupling

The rail is now a controller in `detail-rail/DetailRail.ts`. The main board only passes the selected row and context into `detailRail.open(row, index, context)`. The rail owns its own `/api/prop-detail` request, loading state, error state, and server drilldown rendering. This prevents board-table rendering from knowing about prop-detail fetches or rail internals.

## Build and E2E guardrails

CI now runs:

```bash
npm run build
npm run validate:vite-assets
npm run validate:csp
npm run test:e2e
```

`tools/validate_vite_assets.py` fails if `public/index.html` references `/src/outlier/main.ts`, `/outlier-board.js`, or `/outlier-detail.js`, and verifies that a fingerprinted `/assets/outlier-*.js` bundle exists.

Playwright also validates the runtime path: the production shell must request `/assets/outlier-*.js` and must not request `/outlier-board.js` or `/outlier-detail.js`.
