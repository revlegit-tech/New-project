# Phase 18 v3 — Playerboard Context Contract Repair

This hotfix repairs the bad Phase 18 v2 playerboard patch that could narrow `playerboard_2026.csv` and leave `playerboard.py` with invalid syntax near `PLAYERBOARD_FIELDS`.

It restores the wider backup CSV when available, expands the Playerboard schema without dropping existing columns, and maps Phase 17/18 game context fields through `saved_card_from_row()` so `/api/edge-board` can expose them to the frontend.

It does not add features to legacy `app.py`.
