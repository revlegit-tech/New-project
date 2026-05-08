# Phase 18 v7 — Context Join Match Fix

This patch fixes the final Phase 18 UI contract issue where provider context exists in `data/warehouse/game_context/game_context_DATE.csv`, but `/api/edge-board` still shows blank game-context fields.

Root cause: Playerboard rows use MLB abbreviations such as `SDP` / `STL`, while the canonical game-context file can store full names such as `san diego padres` / `st. louis cardinals`. The EdgeBoard join must normalize both sides before joining.

The patch:

- Replaces `EdgeBoardService._build_payload` with a stable join step.
- Joins canonical game context into board rows by normalized team/opponent.
- Adds full-name and abbreviation aliases for all MLB teams.
- Increases `phase18_context_qa.py` timeout to handle cold local refreshes.
- Adds a Phase 18 hook into `season_auto_collector.py` after Playerboard generation, so future scheduled collector runs fill context automatically.

Do not treat missing OddsPapi as a blocker for current moneyline/game total/weather context. OddsPapi is only needed for opening-line and movement fields.
