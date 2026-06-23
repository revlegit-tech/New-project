from __future__ import annotations

import subprocess
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.daily_workflow_service import DailyWorkflowService


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


class FakeSnapshotWorkflow:
    def run(self, **_kwargs):
        return {"status": "success", "outputs": {}, "warnings": []}


def test_daily_workflow_runs_steps_in_expected_order_with_safe_skips(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seen: list[str] = []

    def runner(name: str, command: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(name)
        return subprocess.CompletedProcess(command, 0, "", "")

    payload = DailyWorkflowService(settings, snapshot_workflow=FakeSnapshotWorkflow(), step_runner=runner).run(date_text="2026-06-23")
    names = [step["name"] for step in payload["steps"]]

    assert names == [
        "collect_actionnetwork_live_snapshot",
        "collect_propline_oddspapi",
        "build_playerboard",
        "build_edge_board",
        "update_mlb_truth_logs",
        "build_actionnetwork_event_bridge",
        "validate_actionnetwork_labels",
        "build_odds_movement_features",
        "build_event_confirmed_training_dataset",
        "score_shadow_models",
    ]
    assert payload["status"] == "success"
    assert payload["steps"][6]["status"] == "skipped"
    assert payload["steps"][9]["reason"] == "missing registry/models or playerboard"
    assert seen == ["build_odds_movement_features"]


def test_daily_workflow_failed_required_script_marks_failed(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    def runner(name: str, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2 if name == "build_odds_movement_features" else 0, "", "")

    payload = DailyWorkflowService(settings, snapshot_workflow=FakeSnapshotWorkflow(), step_runner=runner).run(date_text="2026-06-23")

    assert payload["status"] == "failed"
    assert any(step["name"] == "build_odds_movement_features" and step["status"] == "failed" for step in payload["steps"])
