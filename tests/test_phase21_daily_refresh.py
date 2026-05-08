from __future__ import annotations

from pathlib import Path

from tools.run_daily_refresh import resolve_run_type
from tools.phase21_freshness_report import file_status


def test_resolve_scheduled_windows():
    assert resolve_run_type("scheduled", local_hour=6) == "morning"
    assert resolve_run_type("scheduled", local_hour=12) == "midday"
    assert resolve_run_type("scheduled", local_hour=23) == "midnight"


def test_explicit_run_type_passthrough():
    assert resolve_run_type("manual", local_hour=6) == "manual"
    assert resolve_run_type("grading", local_hour=6) == "grading"


def test_file_status_missing_optional(tmp_path: Path):
    result = file_status("Optional", tmp_path / "missing.csv", required=False)
    assert result["exists"] is False
    assert result["status"] == "optional_missing"
