from __future__ import annotations

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
