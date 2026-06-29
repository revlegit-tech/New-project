from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

import joblib

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


class TinyProbabilityModel:
    def predict_proba(self, matrix: Any) -> Any:
        import numpy as np

        values = np.asarray(matrix, dtype=float)
        probabilities = np.clip(0.25 + (values[:, 0] * 0.05), 0.05, 0.95)
        return np.column_stack([1 - probabilities, probabilities])


def write_model_fixture(settings: Settings, *, market: str = "batter_total_bases", date_label: str = "2026-06-22", rows: int = 220) -> Path:
    artifact_dir = settings.data_dir / "models" / "baseline" / market
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(TinyProbabilityModel(), artifact_dir / "model.joblib")
    (artifact_dir / "feature_columns.json").write_text('["line", "american_odds"]', encoding="utf-8")
    feature_rows = []
    label_rows = []
    for index in range(rows):
        prop_key = f"prop-{index}"
        feature_rows.append(
            {
                "date": date_label,
                "market": market,
                "prop_key": prop_key,
                "player": f"Player {index}",
                "line": str(1 + (index % 4)),
                "american_odds": "-110",
            }
        )
        label_rows.append(
            {
                "date": date_label,
                "market": market,
                "prop_key": prop_key,
                "player": f"Player {index}",
                "line": str(1 + (index % 4)),
                "hit": "1" if index % 3 else "0",
            }
        )
    write_csv(settings.data_dir / "features" / f"prop_features_{date_label}.csv", feature_rows)
    write_csv(settings.data_dir / "warehouse" / "ml_labels" / f"player_prop_labels_{date_label}.csv", label_rows)
    return artifact_dir


def test_calibration_status_missing_when_artifact_absent(tmp_path: Path) -> None:
    payload = ModelCalibrationService(make_settings(tmp_path)).status(date_label="2026-06-24", season=2026, market="batter_hits")

    assert payload["schemaVersion"] == "model-calibration-status.v1"
    assert payload["artifactExists"] is False
    assert payload["calibrationStatus"] == "missing"
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False


def test_calibration_dry_run_scores_model_artifact_feature_rows_and_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    artifact_dir = write_model_fixture(settings)

    payload = ModelCalibrationService(settings).calibrate(date_label="2026-06-22", season=2026, market="batter_total_bases", calibrate=False)

    assert payload["artifactWritten"] is False
    assert payload["metrics"]["sampleCount"] == 220
    assert payload["metrics"]["brierScore"] is not None
    assert payload["metrics"]["logLoss"] is not None
    assert not (artifact_dir / "calibration.json").exists()
    assert not (artifact_dir / "reliability_curve.csv").exists()
    assert not (artifact_dir / "calibration_manifest.json").exists()
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False


def test_calibration_writes_artifacts_when_requested(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    artifact_dir = write_model_fixture(settings)

    payload = ModelCalibrationService(settings).calibrate(date_label="2026-06-22", season=2026, market="batter_total_bases", calibrate=True)

    assert payload["artifactWritten"] is True
    assert payload["calibrationStatus"] == "ready"
    assert (artifact_dir / "calibration.json").is_file()
    assert (artifact_dir / "reliability_curve.csv").is_file()
    assert (artifact_dir / "calibration_manifest.json").is_file()


def test_calibration_missing_model_returns_existing_warning(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    payload = ModelCalibrationService(settings).calibrate(date_label="2026-06-22", season=2026, market="batter_total_bases", calibrate=False)

    assert "Baseline model artifact is missing for this market." in payload["warnings"]
    assert payload["calibrationStatus"] == "missing"


def test_calibration_missing_feature_columns_returns_clear_warning(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    artifact_dir = write_model_fixture(settings)
    (artifact_dir / "feature_columns.json").unlink()

    payload = ModelCalibrationService(settings).calibrate(date_label="2026-06-22", season=2026, market="batter_total_bases", calibrate=False)

    assert "Feature columns manifest is missing or invalid for this market." in payload["warnings"]
    assert payload["calibrationStatus"] == "missing"


def test_calibration_preserves_precomputed_probability_rows_fallback(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    artifact_dir = settings.data_dir / "models" / "baseline" / "batter_hits"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "model.joblib").write_text("not loaded when probability rows exist", encoding="utf-8")
    rows = [
        {"market": "batter_hits", "hit": "1" if index % 2 else "0", "predicted_probability": "0.55"}
        for index in range(20)
    ]
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", rows)

    payload = ModelCalibrationService(settings).calibrate(date_label="2026-06-22", season=2026, market="batter_hits", calibrate=False)

    assert payload["metrics"]["sampleCount"] == 20
    assert not any("Baseline model scoring failed" in warning for warning in payload["warnings"])


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
