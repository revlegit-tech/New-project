from __future__ import annotations

from pathlib import Path

from tools.validate_backup_files import iter_backup_files
from tools.validate_generated_artifacts import find_generated_artifacts


def test_generated_artifact_guard_catches_data_feature_and_model_outputs(tmp_path: Path) -> None:
    for path in (
        tmp_path / "data" / "features" / "prop_features_2026-06-24.csv",
        tmp_path / "data" / "models" / "batter_hits" / "model.pkl",
        tmp_path / "data" / "playerboard" / "playerboard_2026.csv",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")

    offenders = [path.as_posix() for path in find_generated_artifacts(tmp_path)]

    assert "data/features/prop_features_2026-06-24.csv" in offenders
    assert "data/models/batter_hits/model.pkl" in offenders
    assert "data/playerboard/playerboard_2026.csv" in offenders


def test_backup_artifact_guard_catches_backup_and_phasebackup_files(tmp_path: Path) -> None:
    for name in ("table.backup_20260624.csv", "context.phasebackup_20260624.csv"):
        path = tmp_path / "data" / "warehouse" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("backup\n", encoding="utf-8")

    offenders = [path.as_posix() for path in iter_backup_files(tmp_path)]

    assert offenders == [
        "data/warehouse/context.phasebackup_20260624.csv",
        "data/warehouse/table.backup_20260624.csv",
    ]


def test_guards_ignore_workflow_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "workflow-artifacts" / "playerboard_2026.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("artifact\n", encoding="utf-8")

    assert find_generated_artifacts(tmp_path) == []
    assert iter_backup_files(tmp_path) == []
