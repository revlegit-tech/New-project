from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.player_prop_model_calibration_service import PlayerPropModelCalibrationService


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        current_season=2026,
        db_enabled=False,
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def row(index: int, **overrides: Any) -> dict[str, Any]:
    payload = {
        "date": f"2026-06-{(index % 20) + 1:02d}",
        "market": "batter_hits",
        "side": "Over",
        "model_probability_percent": 70 if index % 2 else 30,
        "over": 1 if index % 2 else 0,
    }
    payload.update(overrides)
    return payload


def test_calibration_training_writes_artifact_with_brier_metadata(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    input_path = tmp_path / "historical.csv"
    write_csv(input_path, [row(index) for index in range(30)])

    payload = PlayerPropModelCalibrationService(settings=settings, min_sample=20).calibrate(
        input_path=input_path,
        market="batter_hits",
        method="isotonic",
        min_sample=20,
    )

    assert payload["artifactWritten"] is True
    assert Path(payload["artifactPath"]).exists()
    metrics = payload["metrics"]
    assert metrics["sampleSize"] == 30
    assert "brierScoreBefore" in metrics
    assert "brierScoreAfter" in metrics
    assert "logLossBefore" in metrics
    assert "logLossAfter" in metrics


def test_calibrated_probability_is_clamped_between_zero_and_one(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    input_path = tmp_path / "historical.csv"
    write_csv(input_path, [row(index, model_probability_percent=99 if index % 2 else 1) for index in range(30)])
    service = PlayerPropModelCalibrationService(settings=settings, min_sample=20)
    service.calibrate(input_path=input_path, market="batter_hits", method="isotonic", min_sample=20)

    result = service.apply(market="batter_hits", probability=0.99)

    assert result.status == "applied"
    assert result.calibrated_probability is not None
    assert 0 <= result.calibrated_probability <= 1


def test_calibration_dry_run_reports_insufficient_sample_without_writing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    input_path = tmp_path / "historical.csv"
    write_csv(input_path, [row(index) for index in range(5)])

    payload = PlayerPropModelCalibrationService(settings=settings, min_sample=20).calibrate(
        input_path=input_path,
        market="batter_hits",
        min_sample=20,
        dry_run=True,
    )

    assert payload["artifactWritten"] is False
    assert payload["sampleSize"] == 5
    assert any("sample size is low" in warning for warning in payload["warnings"])
