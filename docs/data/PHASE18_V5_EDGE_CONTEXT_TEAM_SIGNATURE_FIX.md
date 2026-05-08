# Phase 18 v5 — Edge Context Team Signature Fix

This hotfix repairs the `EdgeBoardService` game-context join helper after the v4 repair introduced calls of the form `_context_team(row, "team")` while the local helper still accepted only one positional argument.

The patch appends a compatibility shim to `mlb_app/services/edge_board_service.py` that supports both:

- `_context_team(value)`
- `_context_team(row, "team")`

It does not modify legacy `app.py`.
