# Phase 17 v3 — PropLine Game-Line Match Patch

This patch adds `tools/phase17_apply_propline_game_lines.py`, a defensive joiner that applies PropLine game-line moneyline/total context from:

`data/warehouse/game_context/game_lines_<DATE>.json`

onto:

`data/playerboard/playerboard_<SEASON>.csv`

It does not fabricate moneylines or totals. Team implied runs are only computed when a team moneyline, opponent moneyline, and game total are present.

## Run

```powershell
$Date = "2026-05-07"
python .\tools\phase17_apply_propline_game_lines.py --date $Date --season 2026 --markets batter_hits batter_total_bases
python .\tools\phase17_game_context_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
python .\tools\phase16_live_feature_audit.py --date $Date --season 2026 --markets batter_hits batter_total_bases --write
```

The script writes an audit file:

`data/warehouse/audits/phase17_propline_game_line_match_<DATE>.json`

If `parsedGames` is greater than zero but `matchedRows` remains zero, inspect the audit `unmatchedExamples` and the schema of `game_lines_<DATE>.json`.
