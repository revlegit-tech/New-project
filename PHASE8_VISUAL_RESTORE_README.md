# Phase 8 Visual Restore — Classic Outlier Look

This patch keeps the Phase 8 modular frontend architecture, but restores the previous premium Outlier visual language.

## Why

The first Phase 8 modular shell introduced a new visual treatment that felt too sparse and did not retain the original Outlier betting interface. This correction keeps the safer modular code path while returning to the classic Outlier UX primitives:

- `outlier-app` three-column shell
- `ob-sidebar` with Baseball Edge navigation
- compact trust strip instead of a large dominant trust card
- `ob-hero`, sports tabs, filter shell, category tabs
- high-density `ob-table` board
- sticky right matchup rail
- green/black premium betting-board visual system

## Files changed

- `public/outlier-core.js`
- `public/outlier-board.js`
- `public/outlier-detail.js`
- `public/outlier-ui.css`
- `tests/test_phase8_frontend_architecture.py`

## Preview

```bash
make run
```

Open:

```text
http://localhost:8765/?view=outlier
```

## Safety posture

The restore does **not** bring back unsafe `innerHTML` rendering. The rebuilt classic look still uses DOM construction and `textContent` via shared helpers. The frontend safety linter passes.

## Validation

```bash
node --check public/outlier-core.js
node --check public/outlier-board.js
node --check public/outlier-detail.js
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_phase8_frontend_architecture.py -q
python tools/lint_frontend_safety.py --root .
```
