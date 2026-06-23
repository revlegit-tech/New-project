from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import mlb_app.security.mutation as mutation
from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.security.mutation import TokenBucketRateLimiter


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


@pytest.fixture(autouse=True)
def reset_mutation_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    mutation.mutation_rate_limiter = TokenBucketRateLimiter()
    for key in [
        "MLB_ENV",
        "MLB_APP_ENV",
        "APP_ENV",
        "MLB_DEV_MODE",
        "MLB_MUTATION_TOKEN",
        "MLB_API_TOKEN",
        "MLB_ADMIN_TOKEN",
        "MLB_CSRF_TOKEN",
        "MLB_REQUIRE_CSRF",
        "MLB_MUTATION_RATE_LIMIT",
        "MLB_MUTATION_RATE_WINDOW_SECONDS",
    ]:
        monkeypatch.delenv(key, raising=False)


def write_blocked_shadow_registry(settings: Settings) -> None:
    settings.model_registry_path.parent.mkdir(parents=True, exist_ok=True)
    settings.model_registry_path.write_text(
        json.dumps(
            {
                "batter_hits": {
                    "shadow": {
                        "status": "shadow",
                        "market": "batter_hits",
                        "model_key": "calibrated_logistic",
                        "version": "blocked-v1",
                        "artifact": "data/models/missing/model.joblib",
                        "features": "data/models/missing/feature_schema.json",
                        "training_rows": 10,
                        "positive_rows": 2,
                        "negative_rows": 8,
                        "calibrated": False,
                        "production_gated": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/admin/ml-models/train", {"trainingPath": "data/ml/training.csv"}),
        ("/api/admin/ml-models/evaluate", {"market": "batter_hits"}),
        ("/api/admin/ml-models/promote", {"market": "batter_hits"}),
    ],
)
def test_admin_ml_model_mutations_reject_missing_action_header(
    tmp_path: Path,
    path: str,
    payload: dict[str, Any],
) -> None:
    client = client_for(make_settings(tmp_path))

    response = client.post(path, json=payload)

    assert response.status_code == 403
    assert response.json()["code"] == "action_header_required"


def test_admin_promote_with_header_respects_registry_gates(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_blocked_shadow_registry(settings)
    client = client_for(settings)

    response = client.post(
        "/api/admin/ml-models/promote",
        json={"market": "batter_hits", "sourceStatus": "shadow", "targetStatus": "production"},
        headers={"X-Baseball-Prop-Action": "1"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["result"]["promotion"]["allowed"] is False
    saved = json.loads(settings.model_registry_path.read_text(encoding="utf-8"))
    assert "production" not in saved["batter_hits"]


def test_admin_evaluate_with_header_returns_gate_result(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_blocked_shadow_registry(settings)
    client = client_for(settings)

    response = client.post(
        "/api/admin/ml-models/evaluate",
        json={"market": "batter_hits", "sourceStatus": "shadow", "targetStatus": "production"},
        headers={"X-Baseball-Prop-Action": "1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "evaluate"
    assert payload["result"]["allowed"] is False
