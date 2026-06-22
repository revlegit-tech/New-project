from __future__ import annotations

import pytest

from mlb_app.ml.datasets.feature_matrix_builder import build_feature_matrix
from mlb_app.ml.datasets.leakage_guard import (
    assert_feature_columns_safe,
    assert_no_leakage_columns,
    blocked_ml_feature_fields,
    find_leakage_columns,
)


def test_leakage_guard_rejects_blocked_feature_fields() -> None:
    with pytest.raises(ValueError, match="home_score"):
        assert_no_leakage_columns(["line", "home_score", "gameStatusText"])


def test_leakage_guard_allows_target_prefixed_training_fields_when_requested() -> None:
    assert_no_leakage_columns(["line", "target_result", "target_actual_value"], allow_target_prefixed=True)


def test_feature_columns_reject_target_prefixed_fields() -> None:
    with pytest.raises(ValueError, match="Target-prefixed"):
        assert_feature_columns_safe(["line", "target_hit"])


def test_feature_matrix_builder_drops_target_columns_and_keeps_numeric_features() -> None:
    rows = [
        {"line": "1.5", "model_probability_percent": "58.2", "target_hit": 1, "player": "A"},
        {"line": "2.5", "model_probability_percent": "41.8", "target_hit": 0, "player": "B"},
    ]

    matrix = build_feature_matrix(rows)

    assert list(matrix.columns) == ["line", "model_probability_percent"]
    assert matrix["line"].tolist() == [1.5, 2.5]


def test_blocked_fields_include_critical_postgame_columns() -> None:
    blocked = blocked_ml_feature_fields()

    assert {"result", "actual_value", "profit_1u", "closing_line_value"} <= blocked
    assert find_leakage_columns(["line", "closing_line_value"]) == ["closing_line_value"]
