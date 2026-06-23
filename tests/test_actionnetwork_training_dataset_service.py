from __future__ import annotations

from mlb_app.services.actionnetwork_training_dataset_service import ActionNetworkTrainingDatasetService


def feature_row() -> dict[str, object]:
    return {
        "meta_source": "actionnetwork",
        "meta_game_date": "2026-06-23",
        "meta_event_id": "event-1",
        "meta_player_id": "99",
        "meta_market_group": "alt_hits",
        "meta_market_type": "hits",
        "meta_line": "1.5",
        "meta_bet_side": "over_yes",
        "feature_snapshot_count": 2,
        "feature_latest_american_odds": -100,
    }


def label_row(**overrides: str) -> dict[str, str]:
    row = {
        "source": "actionnetwork",
        "game_date": "2026-06-23",
        "event_id": "event-1",
        "player_id": "99",
        "market_group": "alt_hits",
        "market_type": "hits",
        "line": "1.5",
        "bet_side": "over_yes",
        "gamePk": "game-1",
        "snapshot_id": "snap-1",
        "collection_mode": "live_forward",
        "bridge_status": "confirmed",
        "validation_status": "valid_labeled_event_confirmed",
        "actual_stat": "2",
        "label_result": "win",
        "exclude_from_ml": "0",
    }
    row.update(overrides)
    return row


def test_event_confirmed_live_forward_row_becomes_trainable() -> None:
    rows, summary = ActionNetworkTrainingDatasetService().build_rows(
        labels=[label_row()],
        movement_features=[feature_row()],
    )

    assert len(rows) == 1
    assert rows[0]["target_result"] == "win"
    assert all(key.startswith(("feature_", "target_", "meta_")) for key in rows[0])
    assert summary["trainable_rows"] == 1


def test_date_only_diagnostic_and_push_rows_are_excluded() -> None:
    rows, summary = ActionNetworkTrainingDatasetService().build_rows(
        labels=[
            label_row(collection_mode="diagnostic_past"),
            label_row(label_result="push", exclude_from_ml="1"),
            label_row(validation_status="valid_labeled_date_only_diagnostic", exclude_from_ml="1"),
        ],
        movement_features=[feature_row()],
    )

    assert rows == []
    assert summary["skipped_counts"]["not_live_forward"] == 1
    assert summary["skipped_counts"]["excluded"] == 2
