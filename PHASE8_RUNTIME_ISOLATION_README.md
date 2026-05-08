# Phase 8 Runtime Isolation Patch

This patch fixes the visual-layer overlap problem discovered after the Outlier visual restore.

Previously, `public/index.html` still loaded the full legacy JavaScript stack and then loaded
`/outlier-ui.js` afterward. That meant the Outlier shell visually replaced the old DOM, but legacy
scripts could still run behind it, attach listeners, poll APIs, mutate DOM, or create hidden state.

The new behavior is explicit:

- `/?view=outlier` or `?outlier` loads only `/outlier-ui.js`.
- Normal legacy mode loads the historical script stack.
- `trust-surface.js` is not loaded in Outlier mode because the Outlier shell owns the compact trust strip.
- The legacy `<main class="app-shell">` is hidden immediately in Outlier mode to prevent first-paint bleed-through.

Validation:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_phase8_frontend_architecture.py -q
python tools/lint_frontend_safety.py --root .
```
