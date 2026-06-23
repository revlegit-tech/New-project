from __future__ import annotations

import json
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.model_registry_service import ModelRegistryService


def test_model_registry_requires_exact_market_artifact(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    training_dir = data_dir / "training"
    training_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    (training_dir / "batter_hits_training.csv").write_text(
        "over\n" + "1\n" * 13 + "0\n" * 13,
        encoding="utf-8",
    )
    settings = Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=model_dir / "model_registry.json",
    )

    status = ModelRegistryService(settings).market_status("batter_hits")

    assert status["canTrain"] is True
    assert status["modelTrained"] is False
    assert status["status"] == "not_ready"
    assert status["reason"] == "Missing market-specific model artifact"


def test_model_registry_public_status_uses_relative_paths(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    artifact_path = model_dir / "artifacts" / "batter_hits" / "model.joblib"
    features_path = model_dir / "artifacts" / "batter_hits" / "feature_schema.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"test-model")
    features_path.write_text(
        json.dumps({"schema_version": "test", "feature_names": ["feature_line"], "required_features": ["feature_line"]}),
        encoding="utf-8",
    )
    settings = Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=model_dir / "model_registry.json",
    )
    settings.model_registry_path.write_text(
        json.dumps(
            {
                "batter_hits": {
                    "shadow": {
                        "status": "shadow",
                        "market": "batter_hits",
                        "model_key": "calibrated_logistic",
                        "artifact": artifact_path.relative_to(tmp_path).as_posix(),
                        "features": features_path.relative_to(tmp_path).as_posix(),
                        "training_rows": 500,
                        "positive_rows": 100,
                        "negative_rows": 400,
                        "calibrated": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    status = ModelRegistryService(settings).market_status("batter_hits")

    assert status["modelPath"] == "data/models/artifacts/batter_hits/model.joblib"
    assert status["metadataPath"] == "data/models/artifacts/batter_hits/feature_schema.json"
    assert str(tmp_path) not in json.dumps(status)
