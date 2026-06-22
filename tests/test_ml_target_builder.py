from __future__ import annotations

import pytest

from mlb_app.ml.datasets.target_builder import (
    build_market_binary_target,
    build_market_target,
    build_market_target_rows,
)


def test_pitcher_strikeouts_target_builder_handles_over_under_and_push() -> None:
    rows = [
        {"market": "pitcher_strikeouts", "side": "Over", "line": 6.5, "actual_strikeouts": 8},
        {"market": "pitcher_strikeouts", "side": "Under", "line": 5.5, "actual_strikeouts": 4},
        {"market": "pitcher_strikeouts", "side": "Over", "line": 5, "actual_strikeouts": 5},
    ]

    targets = build_market_target_rows(rows)
    binary = build_market_binary_target(rows)

    assert [target["target_hit"] for target in targets] == [1, 1, None]
    assert targets[2]["target_push"] is True
    assert targets[2]["target_status"] == "push"
    assert binary.tolist() == [1, 1]


def test_batter_hits_under_loss_is_negative_target() -> None:
    target = build_market_target(
        {"market": "batter_hits", "side": "Under", "line": 1.5, "actual_hits": 2}
    )

    assert target.target_hit == 0
    assert target.target_push is False
    assert target.target_status == "graded"


def test_batter_home_runs_yes_style_uses_at_least_one_home_run_without_line() -> None:
    yes_hit = build_market_target({"market": "batter_home_runs", "side": "Yes", "actual_home_runs": 1})
    no_hit = build_market_target({"market": "batter_home_runs", "side": "No", "actual_home_runs": 0})
    yes_miss = build_market_target({"market": "batter_home_runs", "side": "Yes", "actual_home_runs": 0})

    assert yes_hit.target_hit == 1
    assert no_hit.target_hit == 1
    assert yes_miss.target_hit == 0
    assert yes_hit.target_push is False


def test_batter_home_runs_line_market_handles_push() -> None:
    over = build_market_target({"market": "batter_home_runs", "side": "Over", "line": 0.5, "actual_home_runs": 1})
    under = build_market_target({"market": "batter_home_runs", "side": "Under", "line": 0.5, "actual_home_runs": 0})
    push = build_market_target({"market": "batter_home_runs", "side": "Over", "line": 1, "actual_home_runs": 1})

    assert over.target_hit == 1
    assert under.target_hit == 1
    assert push.target_hit is None
    assert push.target_push is True


def test_market_binary_target_uses_target_actual_value_fallback() -> None:
    rows = [
        {"market": "batter_total_bases", "side": "Over", "line": 1.5, "target_actual_value": 2},
        {"market": "batter_total_bases", "side": "Under", "line": 1.5, "target_actual_value": 2},
    ]

    target = build_market_binary_target(rows)

    assert target.tolist() == [1, 0]


def test_market_binary_target_fails_when_only_pushes_are_available() -> None:
    rows = [{"market": "batter_hits", "side": "Over", "line": 1, "actual_hits": 1}]

    with pytest.raises(ValueError, match="No usable market target labels"):
        build_market_binary_target(rows)
