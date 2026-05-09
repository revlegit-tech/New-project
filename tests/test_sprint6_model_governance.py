from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.repositories.model_artifact_repository import ModelArtifactRepository, sha256_file
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.prediction_audit_service import PredictionAuditService


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    model_dir.mkdir(parents=True)
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=model_dir / "model_registry.json",
        db_path=data_dir / "state.sqlite3",
    )


def _write_governed_model(settings: Settings, *, artifact_bytes: bytes = b"model-v1") -> dict[str, str]:
    artifact_dir = settings.model_dir / "artifacts" / "sha256"
    artifact_dir.mkdir(parents=True)
    tmp_artifact = artifact_dir / "tmp.joblib"
    tmp_artifact.write_bytes(artifact_bytes)
    artifact_sha = sha256_file(tmp_artifact)
    artifact_path = artifact_dir / f"{artifact_sha}.joblib"
    tmp_artifact.rename(artifact_path)

    features_payload = {
        "schemaVersion": "features.v1",
        "features": ["recent_hits", "line", "opponent_k_rate"],
        "requiredFeatures": ["recent_hits", "line", "opponent_k_rate"],
    }
    tmp_features = artifact_dir / "tmp.features.json"
    tmp_features.write_text(json.dumps(features_payload), encoding="utf-8")
    features_sha = sha256_file(tmp_features)
    features_path = artifact_dir / f"{features_sha}.features.json"
    tmp_features.rename(features_path)

    metrics_payload = {"graded": 150, "brierScore": 0.21, "logLoss": 0.62}
    tmp_metrics = artifact_dir / "tmp.metrics.json"
    tmp_metrics.write_text(json.dumps(metrics_payload), encoding="utf-8")
    metrics_sha = sha256_file(tmp_metrics)
    metrics_path = artifact_dir / f"{metrics_sha}.metrics.json"
    tmp_metrics.rename(metrics_path)

    (settings.data_dir / "training").mkdir(parents=True)
    (settings.data_dir / "training" / "batter_hits_training.csv").write_text(
        "over\n" + "1\n" * 20 + "0\n" * 20,
        encoding="utf-8",
    )
    settings.model_registry_path.write_text(
        json.dumps(
            {
                "batter_hits": {
                    "production": {
                        "version": "2026.05.08.1",
                        "artifact_sha256": artifact_sha,
                        "features_sha256": features_sha,
                        "metrics_sha256": metrics_sha,
                        "trained_at": "2026-05-08T12:00:00Z",
                        "last_promoted_at": "2026-05-08T13:00:00Z",
                        "training_window": {"start": "2026-03-01", "end": "2026-05-07"},
                        "training_rows": 40,
                        "positive_rows": 20,
                        "negative_rows": 20,
                        "status": "production",
                        "calibrated": True,
                        "backtest": {"graded": 150, "brier_score": 0.21, "log_loss": 0.62},
                        "known_limitations": ["Small early-season sample"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return {"artifact": artifact_sha, "features": features_sha, "metrics": metrics_sha}


def test_content_addressed_artifact_verification_and_feature_schema(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    hashes = _write_governed_model(settings)
    repository = ModelArtifactRepository(settings)

    verification = repository.verify_entry("batter_hits")
    assert verification["ok"] is True
    assert verification["artifact"]["expectedSha256"] == hashes["artifact"]
    assert verification["features"]["verified"] is True

    schema = repository.load_feature_schema("batter_hits")
    assert schema.feature_names == ("recent_hits", "line", "opponent_k_rate")

    valid = repository.validate_feature_columns("batter_hits", ["recent_hits", "line", "opponent_k_rate", "ignored_extra"])
    assert valid.ok is True
    assert valid.extra_features == ("ignored_extra",)

    invalid = repository.validate_feature_columns("batter_hits", ["line", "recent_hits"])
    assert invalid.ok is False
    assert invalid.missing_features == ("opponent_k_rate",)
    assert invalid.order_mismatches


def test_model_registry_blocks_hash_mismatch(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_governed_model(settings)
    payload = json.loads(settings.model_registry_path.read_text(encoding="utf-8"))
    payload["batter_hits"]["production"]["artifact_sha256"] = "0" * 64
    settings.model_registry_path.write_text(json.dumps(payload), encoding="utf-8")

    status = ModelRegistryService(settings).market_status("batter_hits")

    assert status["hashVerified"] is False
    assert status["status"] == "not_ready"
    assert status["reason"] == "Model artifact hash verification failed"


def test_model_card_route_exposes_governance_fields(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    hashes = _write_governed_model(settings)
    client = TestClient(create_app(container=AppContainer(settings=settings)))

    response = client.get("/api/model-cards/batter_hits")
    assert response.status_code == 200
    card = response.json()["markets"][0]
    assert card["version"] == "2026.05.08.1"
    assert card["artifactHashPrefix"] == hashes["artifact"][:12]
    assert card["hashVerified"] is True
    assert card["featureSchema"]["featureNames"] == ["recent_hits", "line", "opponent_k_rate"]
    assert card["knownLimitations"] == ["Small early-season sample"]


def test_prediction_audit_service_writes_append_only_events(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_governed_model(settings)
    service = PredictionAuditService(settings, model_registry_service=ModelRegistryService(settings))

    saved = service.record(
        {
            "market": "batter_hits",
            "gameId": "game-1",
            "playerId": "player-1",
            "input": {"recent_hits": 6, "line": 0.5, "opponent_k_rate": 0.22},
            "outputProbability": 0.61,
            "outputEdge": 0.08,
        }
    )
    duplicate = service.record(saved["event"])
    listed = service.payload({"market": ["batter_hits"]})

    assert saved["status"] == "ok"
    assert duplicate["status"] == "ok"
    assert listed["eventCount"] == 1
    assert listed["events"][0]["artifactSha256"]
