# Outlier Advanced Board Hotfix

This overlay repairs the Phase 8/10 Outlier UI regression without reintroducing the legacy runtime behind the page.

## Fixes

- Restores the high-density prop table behavior with sortable Player, Proposition, Line, Odds, IP, L5, L10, L20, H2H, 2026, and 2025 columns.
- Uses sportsbook implied probability for the `IP` column instead of model probability.
- Makes hit-rate cells tolerant of multiple backend field names and object/numeric/string percent formats.
- Rebuilds the Insights page as a styled dashboard instead of an unstyled readiness dump.
- Adds right-rail Trends and Model views with hit-rate bars, model context, and missing-data flags.
- Keeps all rendering DOM-safe through `textContent` via `createElement`; no unsafe HTML interpolation is added.

## Apply

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\post_phase10_outlier_advanced_board_hotfix.zip" -DestinationPath . -Force
python tools/lint_frontend_safety.py --root .
python -m mlb_app.server 8765 --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:8765/?view=outlier
```
