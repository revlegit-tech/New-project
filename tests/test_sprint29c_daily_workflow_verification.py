from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from scripts.benchmark_playerboard_builder import parse_args
from mlb_app.config import Settings
from mlb_app.services.daily_workflow_service import DailyWorkflowService


class FakeSnapshotWorkflow:
    def run(self, **_kwargs):
        return {"status": "success", "outputs": {}, "warnings": []}


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    data_dir = tmp_path / "data"
    return replace(settings, data_dir=data_dir, db_path=data_dir / "mlb_app_state.sqlite3", current_season=2026)


def test_benchmark_script_parses_args() -> None:
    args = parse_args(["--date", "2026-06-24", "--season", "2026", "--limit", "1000", "--source-mode", "propline", "--no-save", "--workers", "1"])

    assert args.date == "2026-06-24"
    assert args.limit == 1000
    assert args.no_save is True
    assert args.workers == 1


def test_daily_workflow_uses_safe_defaults_and_verifies_collector_check(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    service = DailyWorkflowService(
        settings,
        snapshot_workflow=FakeSnapshotWorkflow(),
        step_runner=lambda _name, _command: subprocess.CompletedProcess(_command, 0, "", ""),
    )

    payload = service.run(date_text="2026-06-24", season=2026)

    assert payload["verificationSummary"]["date"] == "2026-06-24"
    assert payload["verificationSummary"]["readyForProductionTraining"] is False
    assert payload["collectorCheck"]["schemaVersion"] == "collector-check.v1"
    assert __import__("os").environ["PLAYERBOARD_BUILD_WORKERS"] == "1"
