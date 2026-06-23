from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.ml.inference.model_loader import ModelLoader
from mlb_app.ml.inference.prediction_service import ModelPredictionRequest, PredictionService
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


def prediction_service(settings: Settings, *, probability: float = 0.581) -> PredictionService:
    repository = FakeModelArtifactRepository(settings, probability=probability)
    registry_service = ModelRegistryService(settings=settings, artifact_repository=repository)
    loader = ModelLoader(settings=settings, registry_service=registry_service, artifact_repository=repository)
    return PredictionService(settings=settings, model_loader=loader)


def prediction_request(*, model_stage: str = "shadow", existing_final: float | None = None) -> ModelPredictionRequest:
    return ModelPredictionRequest(
        market="pitcher_strikeouts",
        player="Kodai Senga",
        line=5.5,
        side="Over",
        features={"feature_line": 5.5, "feature_recent_rate": 0.64},
        market_probability=0.524,
        context_probability=0.552,
        engine_probability=0.55,
        steam_probability=0.51,
        existing_final_probability_percent=existing_final,
        model_stage=model_stage,
    )


def test_prediction_service_returns_probability(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registered_model(settings)

    result = prediction_service(settings).predict(prediction_request())

    assert result.model_probability == 0.581
    assert result.blended_probability is not None
    assert result.feature_coverage == 1.0
    assert result.as_dict()["modelName"] == "calibrated_logistic"


def test_missing_features_reduce_coverage_and_add_warning(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registered_model(settings)
    request = ModelPredictionRequest(
        market="pitcher_strikeouts",
        features={"feature_line": 5.5},
        market_probability=0.524,
        model_stage="shadow",
    )

    result = prediction_service(settings).predict(request)

    assert result.feature_coverage == 0.5
    assert any("feature coverage" in warning for warning in result.warnings)


def test_shadow_model_does_not_override_production_final_probability(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registered_model(settings, stage="shadow", status="shadow", probability=0.99)

    result = prediction_service(settings, probability=0.99).predict(prediction_request(existing_final=52.4))

    assert result.model_status == "shadow"
    assert result.blended_probability != 0.524
    assert result.model_contributed is False
    assert result.final_probability_percent == 52.4


def test_production_model_can_contribute_through_blender(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registered_model(settings, stage="production", status="production", probability=0.581)

    result = prediction_service(settings).predict(prediction_request(model_stage="production", existing_final=52.4))

    assert result.model_status == "production"
    assert result.model_contributed is True
    assert result.final_probability_percent is not None
    assert result.final_probability_percent != 52.4


def test_public_prediction_response_does_not_expose_local_artifact_paths(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registered_model(settings)

    payload = prediction_service(settings).predict(prediction_request()).as_dict()

    assert str(tmp_path) not in json.dumps(payload)
