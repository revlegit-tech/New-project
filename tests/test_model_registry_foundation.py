from __future__ import annotations

import json
from pathlib import Path

import pytest

from mlb_app.services.model_registry_service import load_training_registry, write_training_registry_entries


def test_registry_loads_missing_and_empty_registry_safely(tmp_path: Path) -> None:
    missing = tmp_path / "model_registry.json"
    empty = tmp_path / "empty_registry.json"
    empty.write_text("", encoding="utf-8")

    assert load_training_registry(missing) == {}
    assert load_training_registry(empty) == {}


def test_registry_writes_candidate_entries_without_production(tmp_path: Path) -> None:
    registry_path = tmp_path / "model_registry.json"

    registry = write_training_registry_entries(
        registry_path,
        [
            {
                "market": "batter_hits",
                "model_key": "logistic",
                "status": "candidate",
                "artifact": "data/models/artifacts/sprint19/batter_hits/logistic/v1/model.joblib",
                "features": "data/models/artifacts/sprint19/batter_hits/logistic/v1/feature_schema.json",
            }
        ],
        status="candidate",
    )

    assert "production" not in registry["batter_hits"]
    assert registry["batter_hits"]["candidate"]["status"] == "candidate"
    assert registry["batter_hits"]["candidate"]["models"]["logistic"]["status"] == "candidate"
    assert json.loads(registry_path.read_text(encoding="utf-8")) == registry


def test_registry_rejects_automatic_production_status(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported model registry status"):
        write_training_registry_entries(
            tmp_path / "model_registry.json",
            [{"market": "batter_hits", "model_key": "logistic", "status": "production"}],
            status="production",
        )
