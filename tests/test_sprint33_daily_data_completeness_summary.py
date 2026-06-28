from __future__ import annotations

import subprocess
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.daily_workflow_service import DailyWorkflowService


class FakeSnapshotWorkflow:
    def run(self, **_kwargs):
        return {"status": "success", "outputs": {}, "warnings": []}


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        db_path=data_dir / "state.sqlite3",
        current_season=2026,
    )


def test_daily_data_completeness_summary_includes_sprint33_statuses(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = DailyWorkflowService(
        settings,
        snapshot_workflow=FakeSnapshotWorkflow(),
        step_runner=lambda name, command: subprocess.CompletedProcess(command, 0, "", ""),
    )

    payload = service.run(date_text="2026-06-24", season=2026)
    summary = payload["dataCompletenessSummary"]

    assert summary["schemaVersion"] == "daily-data-completeness.v1"
    assert {"gameMarkets", "umpire", "featureStore", "asOfAudit", "warnings", "recommendations"} <= set(summary)
    assert summary["gameMarkets"]["status"] == "missing"
    assert summary["umpire"]["status"] == "neutral_fallback"
    assert summary["asOfAudit"]["pregameSafe"] is True
