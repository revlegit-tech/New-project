# Phase 20 v2 — Rail + Modal Hotfix

This patch fixes two Phase 20 QA issues:

1. Selecting a row could open the advanced prop modal while the right rail still showed `Select a prop`.
2. The advanced prop modal left usable space on wide screens and displayed decimal probabilities such as `0.50495` as `0.5%`.

The patch keeps the new `mlb_app` runtime unchanged and only updates frontend contracts/CSS.

## Apply

```powershell
python .\tools\apply_phase20_v2_rail_modal_hotfix.py
python -m py_compile tools/apply_phase20_v2_rail_modal_hotfix.py
python tools/lint_frontend_safety.py --root .
```

Then hard-refresh the browser and test row selection again.
