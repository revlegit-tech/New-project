from __future__ import annotations

import json
from pathlib import Path

import pytest

from mlb_app.ml.registry.artifact_writer import ModelArtifactWriter
from mlb_app.ml.trainers.logistic import LogisticRegressionTrainer


def test_artifact_writer_writes_model_feature_schema_and_metadata(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    features = [
        {"feature_line": 0.5, "feature_recent_rate": 0.20},
        {"feature_line": 0.7, "feature_recent_rate": 0.25},
        {"feature_line": 1.0, "feature_recent_rate": 0.35},
        {"feature_line": 1.4, "feature_recent_rate": 0.60},
        {"feature_line": 1.6, "feature_recent_rate": 0.70},
        {"feature_line": 1.9, "feature_recent_rate": 0.82},
    ]
    target = [0, 0, 0, 1, 1, 1]
    trainer = LogisticRegressionTrainer(
        market="batter_hits",
        model_version="test-v1",
        feature_names=["feature_line", "feature_recent_rate"],
    ).fit(features, target)

    result = ModelArtifactWriter(tmp_path / "artifacts").write(
        market="batter_hits",
        model_key="logistic",
        trainer=trainer,
        model_version="test-v1",
        status="candidate",
        training_rows=6,
        positive_rows=3,
        negative_rows=3,
        target_column="target_hit",
        metrics={"brierScore": 0.2},
        source_dataset="fixture.csv",
    )

    assert result.artifact_path.exists()
    assert result.feature_schema_path.exists()
    assert result.metadata_path.exists()
    schema = json.loads(result.feature_schema_path.read_text(encoding="utf-8"))
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert schema["feature_names"] == ["feature_line", "feature_recent_rate"]
    assert metadata["target_column"] == "target_hit"
    assert result.registry_entry["status"] == "candidate"
    assert result.registry_entry["artifact_sha256"]
