# Phase 18 v4 Edge Context Join Repair

This patch repairs a broken `playerboard.py` caused by a prior schema patch, restores the richer Playerboard CSV backup if available, and wires the canonical `data/warehouse/game_context/game_context_YYYY-MM-DD.csv` file directly into the `EdgeBoardService` response.

The goal is to avoid widening the saved Playerboard schema for game-context fields. Game context remains a separate canonical layer and is joined into API rows at the service boundary for UI display.
