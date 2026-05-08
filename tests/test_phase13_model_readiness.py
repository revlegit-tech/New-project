from __future__ import annotations

import json
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.model_registry_service import ModelRegistryService


def _settings(root: Path) -> Settings:
    return Settings(
        root_dir=root,
        public_dir=root / "public",
        data_dir=root / "data",
        model_dir=root / "data" / "models",
        model_registry_path=root / "data" / "models" / "model_registry.json",
    )


def test_missing_artifact_is_not_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.model_dir.mkdir(parents=True)
    settings.model_registry_path.write_text(json.dumps({"batter_hits": {"status": "production", "calibrated": True}}), encoding="utf-8")

    row = ModelRegistryService(settings).market_status("batter_hits")

    assert row["status"] == "not_ready"
    assert row["productionEligible"] is False
    assert "Missing market-specific model artifact" in row["reason"]


def test_artifact_without_calibration_is_experimental(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    model_dir = settings.model_dir
    training_dir = settings.data_dir / "training"
    model_dir.mkdir(parents=True)
    training_dir.mkdir(parents=True)
    artifact = model_dir / "prop_model_batter_hits.joblib"
    features = model_dir / "prop_model_batter_hits_features.json"
    artifact.write_bytes(b"artifact")
    features.write_text('{"features": ["x"]}', encoding="utf-8")
    rows = ["over,x"] + [f"{i % 2},{i}" for i in range(40)]
    (training_dir / "batter_hits_training.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    settings.model_registry_path.write_text(
        json.dumps(
            {
                "batter_hits": {
                    "artifact": "data/models/prop_model_batter_hits.joblib",
                    "features": "data/models/prop_model_batter_hits_features.json",
                    "status": "production",
                    "calibrated": False,
                    "backtest": {"graded": 200, "brierScore": 0.2, "logLoss": 0.5},
                }
            }
        ),
        encoding="utf-8",
    )

    row = ModelRegistryService(settings).market_status("batter_hits")

    assert row["modelTrained"] is True
    assert row["status"] == "experimental"
    assert row["productionEligible"] is False


def test_calibrated_backtested_candidate_is_production_eligible(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    model_dir = settings.model_dir
    training_dir = settings.data_dir / "training"
    model_dir.mkdir(parents=True)
    training_dir.mkdir(parents=True)
    artifact = model_dir / "prop_model_batter_hits.joblib"
    features = model_dir / "prop_model_batter_hits_features.json"
    artifact.write_bytes(b"artifact")
    features.write_text('{"features": ["x"]}', encoding="utf-8")
    rows = ["over,x"] + [f"{i % 2},{i}" for i in range(80)]
    (training_dir / "batter_hits_training.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    settings.model_registry_path.write_text(
        json.dumps(
            {
                "batter_hits": {
                    "artifact": "data/models/prop_model_batter_hits.joblib",
                    "features": "data/models/prop_model_batter_hits_features.json",
                    "status": "production_candidate",
                    "calibrated": True,
                    "backtest": {"graded": 150, "brierScore": 0.2, "logLoss": 0.5},
                }
            }
        ),
        encoding="utf-8",
    )

    row = ModelRegistryService(settings).market_status("batter_hits")

    assert row["status"] == "production_candidate"
    assert row["productionEligible"] is True
