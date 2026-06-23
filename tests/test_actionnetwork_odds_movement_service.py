from __future__ import annotations

from mlb_app.services.actionnetwork_odds_movement_service import ActionNetworkOddsMovementService


def test_two_snapshots_produce_pregame_delta_features() -> None:
    base = {
        "source": "actionnetwork",
        "game_date": "2026-06-23",
        "event_id": "event-1",
        "player_id": "99",
        "player_name": "Aaron Judge",
        "market_group": "alt_hits",
        "market_type": "hits",
        "line": "1.5",
        "bet_side": "over_yes",
        "book": "Book",
    }
    rows = [
        {**base, "american_odds": "-120", "implied_probability": "0.545455", "snapshot_time": "2026-06-23T12:00:00+00:00"},
        {**base, "american_odds": "-100", "implied_probability": "0.500000", "snapshot_time": "2026-06-23T12:30:00+00:00"},
    ]

    features = ActionNetworkOddsMovementService().build_feature_rows(rows)

    assert features[0]["feature_snapshot_count"] == 2
    assert features[0]["feature_odds_delta_first_to_latest"] == 20
    assert features[0]["feature_minutes_between_first_latest"] == 30
    assert all(key.startswith(("feature_", "meta_")) for key in features[0])
