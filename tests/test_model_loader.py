from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.ml.inference.model_loader import ModelLoader
from mlb_app.repositories.model_artifact_repository import ModelArtifactRepository, sha256_file
from mlb_app.services.model_registry_service import ModelRegistryService


class FakeProbabilityModel:
    def __init__(self, probability: float = 0.581) -> None:
        self.probability = probability

    def predict_proba(self, frame: Any) -> list[list[float]]:
        return [[1.0 - self.probability, self.probability] for _ in range(len(frame))]


class FakeModelArtifactRepository(ModelArtifactRepository):
    def __init__(self, settings: Settings, *, probability: float = 0.581) -> None:
        super().__init__(settings)
        self.probability = probability

    def load_model(self, market: str, *, stage: str = "production", entry: dict[str, Any] | None = None) -> Any:
        return FakeProbabilityModel(self.probability)


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=model_dir / "model_registry.json",
    )


def write_registered_model(
    settings: Settings,
    *,
    market: str = "pitcher_strikeouts",
    stage: str = "shadow",
    status: str | None = None,
    probability: float = 0.581,
) -> None:
    artifact_dir = settings.model_dir / "artifacts" / market / stage
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "model.joblib"
    schema_path = artifact_dir / "feature_schema.json"
    artifact_path.write_text(f"fake-model:{probability}", encoding="utf-8")
    schema_path.write_text(
        json.dumps(
            {
                "schema_version": "test.features.v1",
                "feature_names": ["feature_line", "feature_recent_rate"],
                "required_features": ["feature_line", "feature_recent_rate"],
            }
        ),
        encoding="utf-8",
    )
    selected_status = status or stage
    backtest = {"graded": 100, "brierScore": 0.2, "logLoss": 0.5} if selected_status == "production" else {}
    settings.model_registry_path.parent.mkdir(parents=True, exist_ok=True)
    settings.model_registry_path.write_text(
        json.dumps(
            {
                market: {
                    stage: {
                        "status": selected_status,
                        "market": market,
                        "model_key": "calibrated_logistic",
                        "version": "2026.06.22.1",
                        "artifact": artifact_path.relative_to(settings.root_dir).as_posix(),
                        "features": schema_path.relative_to(settings.root_dir).as_posix(),
                        "artifact_sha256": sha256_file(artifact_path),
                        "features_sha256": sha256_file(schema_path),
                        "training_rows": 500,
                        "positive_rows": 200,
                        "negative_rows": 300,
                        "calibrated": True,
                        "backtest": backtest,
                        "production_gated": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def make_loader(settings: Settings, *, probability: float = 0.581) -> ModelLoader:
    repository = FakeModelArtifactRepository(settings, probability=probability)
    registry_service = ModelRegistryService(settings=settings, artifact_repository=repository)
    return ModelLoader(
        settings=settings,
        registry_service=registry_service,
        artifact_repository=repository,
    )


def test_model_loader_loads_fake_model_and_schema_from_temp_dir(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registered_model(settings)

    loaded = make_loader(settings).load("pitcher_strikeouts", stage="shadow")

    assert loaded.available is True
    assert loaded.model_name == "calibrated_logistic"
    assert loaded.model_version == "2026.06.22.1"
    assert loaded.feature_names == ("feature_line", "feature_recent_rate")


def test_missing_model_returns_safe_unavailable_response(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    loaded = make_loader(settings).load("pitcher_strikeouts", stage="shadow")

    assert loaded.available is False
    assert loaded.model_status == "shadow"
    assert loaded.warnings


def test_model_loader_public_metadata_does_not_expose_absolute_artifact_paths(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registered_model(settings)

    metadata = make_loader(settings).load("pitcher_strikeouts", stage="shadow").public_metadata()

    assert str(tmp_path) not in json.dumps(metadata)
