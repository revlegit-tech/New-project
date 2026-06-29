from __future__ import annotations

import json
from pathlib import Path

from mlb_app.services.atomic_file_service import atomic_write_json, atomic_write_text
from mlb_app.services.workflow_recovery_service import WorkflowRecoveryService


def test_workflow_recovery_skips_fresh_and_reruns_failed_or_missing() -> None:
    plan = WorkflowRecoveryService().plan(
        [
            {"name": "props collection", "status": "ok", "fresh": True},
            {"name": "weather", "status": "failed", "fresh": False},
            {"name": "feature store", "status": "missing"},
        ]
    )

    assert plan[0]["action"] == "skip"
    assert plan[1]["action"] == "rerun"
    assert plan[2]["action"] == "rerun"


def test_workflow_recovery_force_reruns_completed_stages() -> None:
    plan = WorkflowRecoveryService().plan([{"name": "playerboard build", "status": "ok", "fresh": True}], force=True)
    assert plan == [{"name": "playerboard build", "status": "ok", "action": "rerun", "reason": "force requested"}]


def test_recovery_clears_stale_temp_files(tmp_path: Path) -> None:
    temp_file = tmp_path / "data" / "tmp" / ".stage.tmp"
    keep_file = tmp_path / "data" / "tmp" / "summary.json"
    temp_file.parent.mkdir(parents=True)
    temp_file.write_text("temp", encoding="utf-8")
    keep_file.write_text("keep", encoding="utf-8")

    result = WorkflowRecoveryService(temp_roots=[tmp_path / "data"]).clear_stale_temp_files()

    assert temp_file.exists() is False
    assert keep_file.exists()
    assert result["warnings"] == []


def test_atomic_write_does_not_replace_final_when_validation_fails(tmp_path: Path) -> None:
    final = tmp_path / "data" / "status.json"
    final.parent.mkdir(parents=True)
    final.write_text('{"status": "ok"}\n', encoding="utf-8")

    def reject(candidate: Path) -> None:
        json.loads(candidate.read_text(encoding="utf-8"))
        raise ValueError("invalid candidate")

    try:
        atomic_write_text(final, '{"status": "failed"}\n', validator=reject)
    except ValueError:
        pass

    assert final.read_text(encoding="utf-8") == '{"status": "ok"}\n'
    assert list(final.parent.glob("*.tmp")) == []


def test_atomic_write_json_validates_and_replaces(tmp_path: Path) -> None:
    final = tmp_path / "data" / "status.json"
    atomic_write_json(final, {"status": "ok"})
    assert json.loads(final.read_text(encoding="utf-8")) == {"status": "ok"}
