# Phase 8 — Outlier UI Module Split

`public/outlier-ui.js` is now a small opt-in bootstrap. The premium Outlier shell still activates only with:

```text
/?view=outlier
```

The bootstrap loads `outlier-core.js`, and the core module owns shell construction, navigation, the trust-surface host, and primary board activation. Secondary workspaces are lazy-loaded on first use.

## Module map

| Module | Responsibility | Load timing |
|---|---|---|
| `outlier-ui.js` | Compatibility bootstrap from the existing script tag. | On page load, only if `view=outlier`. |
| `outlier-core.js` | Shell, navigation, trust-surface host, shared view state, module loader. | First Outlier load. |
| `outlier-shared.js` | Safe DOM utilities, JSON fetch wrapper, formatters, events. | Imported by modules. |
| `outlier-board.js` | Today/Props/Games primary board workspace. | Immediate primary view. |
| `outlier-detail.js` | Prop detail rail. | Lazy-loaded after row selection. |
| `outlier-picks.js` | My Picks and exposure workspace. | Lazy-loaded on Picks tab. |
| `outlier-model-room.js` | Model cards and data-health dashboard summary. | Lazy-loaded on Model Room/Data Health tabs. |
| `outlier-admin.js` | Quarantine notice for admin workflows. | Lazy-loaded on Admin tab; intentionally does not execute workflows. |

## UX rules preserved

- Primary row data stays visible in the board grid.
- Confidence/readiness stays visible in each row.
- Missing board data renders a visible **Missing Data** state.
- Malformed or unavailable status renders **Research Only**, not a generic fallback.
- Request IDs are displayed only in operational metadata/error contexts.

## Safety rule

Outlier modules must construct DOM nodes with `document.createElement()` and assign API strings using `textContent`. The lint command checks trust-critical modules:

```bash
python tools/lint_frontend_safety.py --root .
```

The default scan targets:

```text
public/outlier-*.js
public/trust-surface.js
```

Use explicit allow markers only for audited static markup that cannot contain API-sourced values.
