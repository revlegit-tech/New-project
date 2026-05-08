from __future__ import annotations

import pytest

from mlb_app.services.time_validation import assert_no_postgame_leakage, chronological_train_validation_split


def test_chronological_split_never_randomizes_future_rows() -> None:
    rows = [
        {"date": "2026-05-01", "feature": 1},
        {"date": "2026-05-02", "feature": 2},
        {"date": "2026-05-03", "feature": 3},
        {"date": "2026-05-04", "feature": 4},
        {"date": "2026-05-05", "feature": 5},
    ]

    split = chronological_train_validation_split(rows, validation_fraction=0.4)

    assert [row["date"] for row in split.train_rows] == ["2026-05-01", "2026-05-02", "2026-05-03"]
    assert [row["date"] for row in split.validation_rows] == ["2026-05-04", "2026-05-05"]
    assert split.metadata()["strategy"] == "chronological"


def test_leakage_guard_blocks_postgame_columns() -> None:
    with pytest.raises(ValueError):
        assert_no_postgame_leakage(["player", "line", "actual_hits"])
