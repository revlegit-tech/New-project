from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.contracts.feature_store_schema import postgame_label_names, pregame_feature_names
from mlb_app.services.model_training_readiness_service import ModelTrainingReadinessService


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_gate_fixture(settings: Settings, *, date_label: str, leakage: bool = False) -> Path:
    fields = list(pregame_feature_names())
    row = {field: "" for field in fields}
    row.update({"date": date_label, "season": 2026, "player": "Player 1", "team": "NYY", "market": "batter_hits"})
    if leakage:
        leaked = sorted(postgame_label_names())[0]
        fields.append(leaked)
        row[leaked] = "1"
    write_csv(settings.data_dir / "features" / f"prop_features_{date_label}.csv", [row], fields)
    labels = [
        {"date": date_label, "market": "batter_hits", "hit": "1" if index % 2 else "0", "result": "hit" if index % 2 else "miss"}
        for index in range(500)
    ]
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", labels)
    artifact_dir = settings.data_dir / "models" / "baseline" / "batter_hits"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "model.joblib").write_text("fixture", encoding="utf-8")
    (artifact_dir / "feature_columns.json").write_text(json.dumps(["hit_rate_10"]), encoding="utf-8")
    return artifact_dir


def write_calibration(artifact_dir: Path) -> None:
    (artifact_dir / "calibration.json").write_text(
        json.dumps({"sampleCount": 500, "brierScore": 0.21, "logLoss": 0.62, "expectedCalibrationError": 0.03}),
        encoding="utf-8",
    )


def write_backtest(artifact_dir: Path) -> None:
    (artifact_dir / "backtest_metrics.json").write_text(
        json.dumps({"evaluatedRows": 500, "coverage": 1.0, "averageEdge": 0.01}),
        encoding="utf-8",
    )


def test_production_readiness_false_without_calibration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )
    settings = make_settings(tmp_path)
    artifact_dir = write_gate_fixture(settings, date_label="2026-06-24")
    write_backtest(artifact_dir)

    market = ModelTrainingReadinessService(settings).payload(date_label="2026-06-24", season=2026, market="batter_hits")["markets"][0]

    assert market["productionEligible"] is False
    assert market["calibrationStatus"] == "missing"


def test_production_readiness_false_without_backtest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )
    settings = make_settings(tmp_path)
    artifact_dir = write_gate_fixture(settings, date_label="2026-06-24")
    write_calibration(artifact_dir)

    market = ModelTrainingReadinessService(settings).payload(date_label="2026-06-24", season=2026, market="batter_hits")["markets"][0]

    assert market["productionEligible"] is False
    assert market["backtestStatus"] == "missing"


def test_production_readiness_false_with_leakage_violation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )
    settings = make_settings(tmp_path)
    artifact_dir = write_gate_fixture(settings, date_label="2026-06-24", leakage=True)
    write_calibration(artifact_dir)
    write_backtest(artifact_dir)

    payload = ModelTrainingReadinessService(settings).payload(date_label="2026-06-24", season=2026, market="batter_hits")

    assert payload["featureMatrix"]["leakagePolicyOk"] is False
    assert payload["markets"][0]["productionEligible"] is False


def test_production_readiness_true_only_when_every_gate_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )
    settings = make_settings(tmp_path)
    artifact_dir = write_gate_fixture(settings, date_label="2026-06-24")
    write_calibration(artifact_dir)
    write_backtest(artifact_dir)

    payload = ModelTrainingReadinessService(settings).payload(date_label="2026-06-24", season=2026, market="batter_hits")
    market = payload["markets"][0]

    assert payload["readyForProductionTraining"] is True
    assert market["productionEligible"] is True
    assert market["calibrationStatus"] == "ready"
    assert market["backtestStatus"] == "ready"
