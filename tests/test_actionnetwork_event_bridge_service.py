from __future__ import annotations

from mlb_app.services.actionnetwork_event_bridge_service import ActionNetworkEventBridgeService


def odds_row(event_id: str, player: str) -> dict[str, str]:
    return {"game_date": "2026-06-23", "event_id": event_id, "player_name": player, "snapshot_id": "snap-1"}


def truth_row(game_pk: str, player: str) -> dict[str, str]:
    return {"date": "2026-06-23", "gamePk": game_pk, "player": player}


def test_confirmed_event_bridge_requires_unique_game_overlap() -> None:
    players = [f"Player {idx}" for idx in range(1, 10)]
    rows = ActionNetworkEventBridgeService().build_rows(
        odds_rows=[odds_row("event-1", player) for player in players],
        batter_rows=[truth_row("game-1", player) for player in players],
        pitcher_rows=[],
        team_rows=[],
    )

    assert rows[0]["bridge_status"] == "confirmed"
    assert rows[0]["gamePk"] == "game-1"
    assert rows[0]["exclude_from_ml"] == "0"


def test_duplicate_best_game_pk_bridge_is_rejected() -> None:
    players = [f"Player {idx}" for idx in range(1, 10)]
    rows = ActionNetworkEventBridgeService().build_rows(
        odds_rows=[odds_row("event-1", player) for player in players],
        batter_rows=[
            *[truth_row("game-1", player) for player in players],
            *[truth_row("game-2", player) for player in players],
        ],
        pitcher_rows=[],
        team_rows=[],
    )

    assert rows[0]["bridge_status"] == "rejected"
    assert rows[0]["exclude_reason"] == "duplicate_best_gamePk"


def test_mixed_event_dirty_case_is_rejected_for_low_overlap() -> None:
    event_players = [f"NYY {idx}" for idx in range(1, 5)] + [f"DET {idx}" for idx in range(1, 5)]
    rows = ActionNetworkEventBridgeService().build_rows(
        odds_rows=[odds_row("event-1", player) for player in event_players],
        batter_rows=[
            *[truth_row("game-nyy", f"NYY {idx}") for idx in range(1, 5)],
            *[truth_row("game-det", f"DET {idx}") for idx in range(1, 5)],
        ],
        pitcher_rows=[],
        team_rows=[],
    )

    assert rows[0]["bridge_status"] == "rejected"
    assert rows[0]["exclude_from_ml"] == "1"
