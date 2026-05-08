from __future__ import annotations

import json
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.product_state_service import ProductStateService


def test_product_state_defaults_to_research_mode(tmp_path: Path) -> None:
    settings = Settings.from_env(tmp_path)
    payload = ProductStateService(settings).payload()

    assert payload["state"] == "research_mode"
    assert payload["researchMode"] is True
    assert "Potential edge" not in payload["allowedDecisionLabels"]
    assert "Watchlist" in payload["allowedDecisionLabels"]


def test_grading_state_not_started_without_summary(tmp_path: Path) -> None:
    settings = Settings.from_env(tmp_path)
    payload = GradingStateService(settings, data_dir=tmp_path / "data").payload({"date": ["2026-05-06"]})

    assert payload["state"] == "not_started"
    assert payload["ok"] is False
    assert payload["latestFullyGradedDate"] == ""


def test_grading_state_marks_latest_fully_graded_date(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    health_dir = data_dir / "health"
    health_dir.mkdir(parents=True)
    (health_dir / "latest_grading_summary.json").write_text(
        json.dumps(
            {
                "checkedAt": "2026-05-07T04:30:00+00:00",
                "date": "2026-05-06",
                "ok": True,
                "counts": {
                    "backtestRowsForDate": 12,
                    "gradedBacktestRowsForDate": 12,
                    "mlRowsForDate": 4,
                    "gradedMlRowsForDate": 4,
                },
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    payload = GradingStateService(Settings.from_env(tmp_path), data_dir=data_dir).payload({"date": ["2026-05-06"]})

    assert payload["state"] == "graded"
    assert payload["ok"] is True
    assert payload["latestFullyGradedDate"] == "2026-05-06"


def test_grading_state_partial_when_requested_date_is_newer_than_summary(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    health_dir = data_dir / "health"
    health_dir.mkdir(parents=True)
    (health_dir / "latest_grading_summary.json").write_text(
        json.dumps(
            {
                "checkedAt": "2026-05-07T04:30:00+00:00",
                "date": "2026-05-05",
                "ok": True,
                "counts": {
                    "backtestRowsForDate": 10,
                    "gradedBacktestRowsForDate": 10,
                    "mlRowsForDate": 0,
                    "gradedMlRowsForDate": 0,
                },
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    payload = GradingStateService(Settings.from_env(tmp_path), data_dir=data_dir).payload({"date": ["2026-05-06"]})

    assert payload["state"] == "partial"
    assert payload["ok"] is True
    assert payload["latestFullyGradedDate"] == ""
    assert "not requested date" in payload["warnings"][0]
