from __future__ import annotations

from mlb_app.ml.evaluation.clv import assert_clv_not_in_features, average_clv
from mlb_app.ml.evaluation.roi import roi_by_edge_bucket


def test_roi_by_edge_bucket_is_generated() -> None:
    rows = [
        {"edge": 0.03, "target_profit_1u": 0.9},
        {"edge": 0.07, "target_profit_1u": -1.0},
        {"edge": -0.01, "target_profit_1u": 0.8},
    ]

    buckets = roi_by_edge_bucket(rows)

    assert [bucket["bucket"] for bucket in buckets] == ["negative", "0_to_2", "2_to_5", "5_to_10", "10_plus"]
    assert buckets[2]["profit1u"] == 0.9
    assert buckets[3]["roi"] == -1.0


def test_clv_is_ignored_if_missing_and_blocked_as_feature() -> None:
    report = average_clv([{"target_hit": 1}])

    assert report["available"] is False
    try:
        assert_clv_not_in_features(["feature_closing_line_value"])
    except ValueError as error:
        assert "evaluation-only" in str(error)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("CLV feature should be rejected")
