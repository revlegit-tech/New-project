from __future__ import annotations

import pytest

from mlb_app.ml.datasets.feature_matrix_builder import build_feature_matrix
from mlb_app.ml.datasets.leakage_guard import assert_training_row_contract
from mlb_app.ml.datasets.target_builder import build_binary_target


def test_prefixed_training_row_passes_contract() -> None:
    assert_training_row_contract(
        {
            "feature_line": 1.5,
            "feature_odds": -110,
            "feature_no_vig_probability": 0.52,
            "target_actual_value": 2,
            "target_hit": 1,
            "target_push": False,
            "meta_game_date": "2026-06-22",
            "meta_player": "Aaron Judge",
        }
    )


def test_unprefixed_result_and_actual_value_fail_contract() -> None:
    with pytest.raises(ValueError, match="feature_, target_, or meta_"):
        assert_training_row_contract(
            {
                "feature_line": 1.5,
                "target_hit": 1,
                "meta_player": "Aaron Judge",
                "result": "win",
                "actual_value": 2,
            }
        )


def test_feature_matrix_does_not_include_targets_or_metadata() -> None:
    rows = [
        {
            "feature_line": "1.5",
            "feature_projected_plate_appearances": "4.3",
            "target_hit": 1,
            "target_result": "win",
            "meta_player": "Aaron Judge",
            "meta_book": "ExampleBook",
        }
    ]

    matrix = build_feature_matrix(rows)

    assert list(matrix.columns) == ["feature_line", "feature_projected_plate_appearances"]


def test_target_vector_comes_from_target_hit_by_default() -> None:
    target = build_binary_target(
        [
            {"feature_line": 1.5, "target_hit": 1, "target_result": "win"},
            {"feature_line": 1.5, "target_hit": 0, "target_result": "loss"},
        ]
    )

    assert target.tolist() == [1, 0]


def test_target_vector_can_use_configured_target_column() -> None:
    target = build_binary_target(
        [
            {"feature_line": 1.5, "target_hit": 0, "target_result": "win"},
            {"feature_line": 1.5, "target_hit": 1, "target_result": "loss"},
        ],
        target_column="target_result",
    )

    assert target.tolist() == [1, 0]


def test_unprefixed_configured_target_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="target_"):
        build_binary_target([{"hit": 1}], target_column="hit")
