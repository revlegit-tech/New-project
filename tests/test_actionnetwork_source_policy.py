from __future__ import annotations

from datetime import date

import pytest

from mlb_app.services.actionnetwork_source_policy import resolve_collection_policy


def test_current_day_collection_is_live_forward() -> None:
    policy = resolve_collection_policy("2026-06-23", today=date(2026, 6, 23))

    assert policy.collection_mode == "live_forward"
    assert policy.exclude_from_ml == "0"
    assert policy.exclude_reason == ""


def test_past_date_rejected_without_diagnostic_flag() -> None:
    with pytest.raises(ValueError, match="forward-only"):
        resolve_collection_policy("2026-06-22", today=date(2026, 6, 23))


def test_past_date_diagnostic_is_excluded_from_ml() -> None:
    policy = resolve_collection_policy(
        "2026-06-22",
        allow_past_diagnostic=True,
        today=date(2026, 6, 23),
    )

    assert policy.collection_mode == "diagnostic_past"
    assert policy.exclude_from_ml == "1"
    assert policy.exclude_reason == "actionnetwork_past_diagnostic"
