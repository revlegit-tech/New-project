from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=model_dir / "model_registry.json",
        db_path=data_dir / "state.sqlite3",
        current_season=2026,
    )


def client_for(settings: Settings) -> TestClient:
    return TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))


def write_registry(settings: Settings) -> None:
    artifact_path = settings.model_dir / "artifacts" / "batter_hits" / "shadow" / "model.joblib"
    schema_path = artifact_path.with_name("feature_schema.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("fake-model", encoding="utf-8")
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
    settings.model_registry_path.parent.mkdir(parents=True, exist_ok=True)
    settings.model_registry_path.write_text(
        json.dumps(
            {
                "batter_hits": {
                    "shadow": {
                        "status": "shadow",
                        "market": "batter_hits",
                        "model_key": "calibrated_logistic",
                        "version": "test-v1",
                        "artifact": str(artifact_path),
                        "features": str(schema_path),
                        "training_rows": 500,
                        "positive_rows": 220,
                        "negative_rows": 280,
                        "feature_count": 2,
                        "calibrated": True,
                        "metrics": {"brierScore": 0.2, "logLoss": 0.55},
                        "backtest": {"graded": 120, "roiPercent": 4.2},
                        "production_gated": True,
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


class FakePredictionResult:
    def as_dict(self) -> dict[str, Any]:
        return {
            "market": "batter_hits",
            "player": "Aaron Judge",
            "modelProbability": 0.61,
            "marketProbability": 0.53,
            "blendedProbability": 0.57,
            "modelName": "fake-model",
            "modelVersion": "test-v1",
            "modelStatus": "shadow",
            "featureCoverage": 1.0,
            "modelContributed": False,
            "finalProbabilityPercent": 53.0,
            "warnings": ["shadow predictions do not alter final probability"],
        }


class FakePredictionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.seen_request: dict[str, Any] = {}

    def predict(self, request: dict[str, Any]) -> FakePredictionResult:
        self.seen_request = request
        return FakePredictionResult()


def test_public_status_returns_200_with_empty_registry(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = client_for(settings)

    response = client.get("/api/ml-models/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["schemaVersion"] == "ml-models.v1"
    assert payload["registry"]["entryCount"] == 0
    assert payload["markets"] == []


def test_registry_endpoint_returns_safe_entries(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    client = client_for(settings)

    response = client.get("/api/ml-models/registry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entryCount"] == 1
    first = payload["entries"][0]
    assert first["market"] == "batter_hits"
    assert first["stage"] == "shadow"
    assert first["modelKey"] == "calibrated_logistic"
    assert "artifact" not in first
    assert str(tmp_path) not in json.dumps(payload)


def test_metrics_and_feature_coverage_endpoints(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    client = client_for(settings)

    metrics = client.get("/api/ml-models/metrics").json()
    coverage = client.get(
        "/api/ml-models/feature-coverage?feature_line=0.5&feature_recent_rate=0.62"
    ).json()

    assert metrics["metricCount"] == 1
    assert metrics["metrics"][0]["hasMetrics"] is True
    assert coverage["entryCount"] == 1
    assert coverage["coverage"][0]["featureCoverage"] == 1.0


def test_prediction_preview_works_with_fake_prediction_service(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    container = AppContainer(settings=settings)
    fake_service = FakePredictionService(settings)
    container.prediction_service = fake_service  # type: ignore[assignment]
    client = TestClient(create_app(container=container), client=("127.0.0.1", 50000))

    response = client.get(
        "/api/ml-models/predictions/preview"
        "?market=batter_hits&player=Aaron%20Judge&feature_line=0.5&feature_recent_rate=0.62"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["preview"]["modelProbability"] == 0.61
    assert payload["preview"]["modelContributed"] is False
    assert fake_service.seen_request["features"]["feature_line"] == 0.5


def test_ml_model_endpoints_appear_in_openapi(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = client_for(settings)
    schema = client.app.openapi()

    for path in [
        "/api/ml-models/status",
        "/api/ml-models/registry",
        "/api/ml-models/metrics",
        "/api/ml-models/feature-coverage",
        "/api/ml-models/predictions/preview",
        "/api/admin/ml-models/train",
        "/api/admin/ml-models/evaluate",
        "/api/admin/ml-models/promote",
    ]:
        assert path in schema["paths"]

    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
