from __future__ import annotations

from mlb_app.ml.evaluation.walk_forward import date_ordered_splits, evaluate_walk_forward


def _rows() -> list[dict[str, object]]:
    return [
        {
            "meta_game_date": f"2026-05-{day:02d}",
            "meta_market": "batter_hits",
            "feature_line": 0.5,
            "target_hit": 1 if day % 2 else 0,
            "model_probability": 0.7 if day % 2 else 0.3,
            "edge": 0.04,
        }
        for day in range(1, 9)
    ]


def test_walk_forward_splitter_never_trains_on_future_rows() -> None:
    splits = date_ordered_splits(_rows(), min_train_rows=4, validation_window=2)

    assert splits
    for split in splits:
        assert split.train_end_date < split.validation_start_date


def test_walk_forward_report_is_deterministic() -> None:
    report = evaluate_walk_forward(_rows(), min_train_rows=4, validation_window=2)

    assert report["status"] == "ok"
    assert report["summary"]["brierScore"] == 0.09
    assert report["summary"]["calibration"]["bucketCount"] == 10
    assert report["summary"]["clv"]["available"] is False


def test_empty_and_small_datasets_return_safe_warnings() -> None:
    assert evaluate_walk_forward([])["warnings"] == ["empty dataset"]
    assert "not enough dated rows" in evaluate_walk_forward(_rows()[:2], min_train_rows=4)["warnings"][0]


def test_clv_is_not_allowed_in_feature_context() -> None:
    rows = _rows()
    rows[0]["feature_closing_line_value"] = 1.2

    try:
        evaluate_walk_forward(rows, min_train_rows=4, validation_window=2)
    except ValueError as error:
        assert "CLV is evaluation-only" in str(error)
    else:  # pragma: no cover
        raise AssertionError("CLV leakage should be rejected")
