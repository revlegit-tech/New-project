# Phase 8 Cumulative Overlay — Frontend Architecture and Luxury UI Refactor

This bundle is cumulative through Phase 7 and adds the first Phase 8 frontend split.

## What changed

- `public/outlier-ui.js` is now a small compatibility bootstrap.
- `public/outlier-core.js` owns the premium shell, navigation, trust host, and module loading.
- `public/outlier-board.js` renders the primary board immediately.
- `public/outlier-detail.js`, `public/outlier-picks.js`, `public/outlier-model-room.js`, and `public/outlier-admin.js` lazy-load on demand.
- `public/outlier-shared.js` centralizes safe DOM helpers, fetch handling, formatting, and events.
- `tools/lint_frontend_safety.py` blocks unsafe rendering patterns in trust-critical frontend modules.
- `docs/frontend/OUTLIER_MODULE_SPLIT.md` documents the module contract.

## Run locally

```bash
make run
```

Open the default app:

```text
http://localhost:8765
```

Preview the modular Outlier shell:

```text
http://localhost:8765/?view=outlier
```

## Validation

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_phase8_frontend_architecture.py -q
python tools/lint_frontend_safety.py --root .
```

## Notes

This phase starts the split without introducing new betting markets. Admin workflows remain quarantined and non-executable from the bettor-facing shell.
