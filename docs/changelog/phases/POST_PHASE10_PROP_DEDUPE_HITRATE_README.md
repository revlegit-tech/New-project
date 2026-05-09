# Post Phase 10: Prop Deduplication + Hit-Rate UI Cleanup

This hotfix should be applied after `post_phase10_data_fresh_advanced_detail_hotfix_v2.zip`.

## What it fixes

- Collapses duplicate board rows caused by the same player/market/line appearing at multiple sportsbooks.
- Keeps one clean prop card per identity and stores all book prices in a `books` ladder.
- Displays the best available price in the board with a `Best of N` book count.
- Preserves multi-book pricing for the advanced Prop Detail price comparison.
- Normalizes common team aliases such as `SD` -> `SDP`, reducing duplicate Padres rows.
- Fixes PropLine one-sided labels:
  - `Yes`, `1+`, and player-name outcomes become `Over`.
  - `No` becomes `Under`.
- Fixes hit-rate direction for home runs and other one-sided PropLine player props so L5/L10/L20 are computed from real game-log stats using the correct Over/Under side.

## Refresh command

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"
python .\tools\refresh_outlier_slate.py --date $Date --season 2026 --limit 500 --source-mode canonical
```

Restart the app and open:

```text
http://127.0.0.1:8765/?view=outlier
```
