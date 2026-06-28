from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.model_calibration_service import ModelCalibrationService
from scripts.calibrate_baseline_model import main as calibrate_main


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_calibration_status_missing_when_artifact_absent(tmp_path: Path) -> None:
    payload = ModelCalibrationService(make_settings(tmp_path)).status(date_label="2026-06-24", season=2026, market="batter_hits")

    assert payload["schemaVersion"] == "model-calibration-status.v1"
    assert payload["artifactExists"] is False
    assert payload["calibrationStatus"] == "missing"
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False


def test_calibration_dry_run_script_does_not_write_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLB_DATA_DIR", str(tmp_path / "data"))
    artifact_dir = tmp_path / "data" / "models" / "baseline" / "batter_hits"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "model.joblib").write_text("fixture", encoding="utf-8")
    rows = [
        {"market": "batter_hits", "hit": "1" if index % 2 else "0", "predicted_probability": "0.55"}
        for index in range(20)
    ]
    write_csv(tmp_path / "data" / "labels" / "player_prop_labels_2026.csv", rows)

    assert calibrate_main(["--season", "2026", "--market", "batter_hits", "--dry-run"]) == 0

    assert not (artifact_dir / "calibration.json").exists()
    assert not (artifact_dir / "reliability_curve.csv").exists()
    assert not (artifact_dir / "calibration_manifest.json").exists()
