from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from mlb_app.config import Settings
from mlb_app.ml.registry.artifact_writer import ModelArtifactWriter
from mlb_app.services.model_training_service import ModelTrainingService


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


def tiny_rows() -> list[dict[str, object]]:
    values = [
        (0.5, 0.20, 0),
        (0.7, 0.25, 0),
        (1.0, 0.35, 0),
        (1.4, 0.60, 1),
        (1.6, 0.70, 1),
        (1.9, 0.82, 1),
    ]
    rows = []
    for index, (line, recent_rate, hit) in enumerate(values, start=1):
        rows.append(
            {
                "meta_market": "batter_hits",
                "meta_player": f"Player {index}",
                "meta_training_join_key": f"row-{index}",
                "feature_line": line,
                "feature_recent_rate": recent_rate,
                "target_hit": hit,
                "target_actual_value": hit,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_training_runner_selects_only_feature_columns_and_writes_candidate_artifacts(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    settings = make_settings(tmp_path)
    training_path = tmp_path / "training.csv"
    write_csv(training_path, tiny_rows())
    service = ModelTrainingService(
        settings=settings,
        artifact_writer=ModelArtifactWriter(tmp_path / "artifacts"),
    )

    result = service.train_from_dataset(
        training_path=training_path,
        markets=["batter_hits"],
        model_keys=["logistic", "calibrated_logistic"],
        model_version="test-v1",
        registry_status="candidate",
        test_mode=True,
    )

    market = result.markets[0]
    assert result.status == "trained"
    assert market.feature_names == ("feature_line", "feature_recent_rate")
    assert market.target_column == "target_hit"
    assert len(market.trained_artifacts) == 2
    schema = json.loads(market.trained_artifacts[0].feature_schema_path.read_text(encoding="utf-8"))
    assert schema["feature_names"] == ["feature_line", "feature_recent_rate"]
    registry = json.loads(settings.model_registry_path.read_text(encoding="utf-8"))
    assert "production" not in registry["batter_hits"]
    assert set(registry["batter_hits"]["candidate"]["models"]) == {"logistic", "calibrated_logistic"}


def test_training_runner_excludes_meta_and_target_fields_from_model_training(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    settings = make_settings(tmp_path)
    training_path = tmp_path / "training.csv"
    rows = tiny_rows()
    for row in rows:
        row["meta_numeric_noise"] = 999
        row["target_profit_1u"] = 1
    write_csv(training_path, rows)

    result = ModelTrainingService(
        settings=settings,
        artifact_writer=ModelArtifactWriter(tmp_path / "artifacts"),
    ).train_from_dataset(
        training_path=training_path,
        markets=["batter_hits"],
        model_keys=["logistic"],
        model_version="test-v1",
        registry_status="shadow",
        test_mode=True,
    )

    assert result.markets[0].feature_names == ("feature_line", "feature_recent_rate")
    assert result.markets[0].trained_artifacts[0].registry_entry["status"] == "shadow"


def test_training_runner_blocks_unprefixed_leakage_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    training_path = tmp_path / "training.csv"
    rows = tiny_rows()
    rows[0]["home_score"] = 7
    write_csv(training_path, rows)

    with pytest.raises(ValueError, match="feature_, target_, or meta_"):
        ModelTrainingService(settings=settings).train_from_dataset(training_path=training_path, test_mode=True)


def test_training_runner_blocks_feature_prefixed_leakage_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    training_path = tmp_path / "training.csv"
    rows = tiny_rows()
    rows[0]["feature_actual_value"] = 2
    write_csv(training_path, rows)

    with pytest.raises(ValueError, match="Blocked leakage fields"):
        ModelTrainingService(settings=settings).train_from_dataset(training_path=training_path, test_mode=True)


def test_single_class_target_blocks_training(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    training_path = tmp_path / "training.csv"
    rows = tiny_rows()
    for row in rows:
        row["target_hit"] = 1
    write_csv(training_path, rows)

    result = ModelTrainingService(settings=settings).train_from_dataset(
        training_path=training_path,
        markets=["batter_hits"],
        model_keys=["logistic"],
        test_mode=True,
    )

    assert result.status == "skipped"
    assert result.markets[0].reason == "training targets must contain both positive and negative classes"


def test_xgboost_unavailable_does_not_break_training_service_import() -> None:
    from mlb_app.services import model_training_service

    assert hasattr(model_training_service, "ModelTrainingService")
