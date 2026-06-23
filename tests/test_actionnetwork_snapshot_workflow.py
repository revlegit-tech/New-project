from __future__ import annotations

import subprocess
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.actionnetwork_snapshot_status_service import ActionNetworkSnapshotWorkflow


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


def test_workflow_calls_collector_once_and_records_outputs(tmp_path: Path) -> None:
    calls = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="saved_csv=data/warehouse/normalized/odds/actionnetwork_all_markets_2026-06-23.csv\nsaved_snapshot_csv=data/warehouse/normalized/odds/actionnetwork_all_markets_2026-06-23_120000.csv\n", stderr="")

    settings = make_settings(tmp_path)
    payload = ActionNetworkSnapshotWorkflow(settings, command_runner=runner).run(date_text="2026-06-23")

    assert len(calls) == 1
    assert payload["status"] == "success"
    assert payload["outputs"]["saved_csv"].endswith("actionnetwork_all_markets_2026-06-23.csv")
    assert (settings.data_dir / "status" / "actionnetwork_live_snapshot_status.json").exists()


def test_workflow_lock_blocks_overlap_and_stale_lock_recovers(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    lock = settings.data_dir / "status" / "actionnetwork_live_snapshot.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("{}", encoding="utf-8")
    workflow = ActionNetworkSnapshotWorkflow(settings, command_runner=lambda command: subprocess.CompletedProcess(command, 0, "", ""))

    blocked = workflow.run(date_text="2026-06-23")
    assert blocked["status"] == "skipped"

    import os
    os.utime(lock, (1, 1))
    recovered = workflow.run(date_text="2026-06-23")
    assert recovered["status"] == "success"
    assert "Recovered stale lock" in " ".join(recovered["warnings"])
