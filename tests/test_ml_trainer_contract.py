from __future__ import annotations

from pathlib import Path

import pytest

from mlb_app.ml.trainers.base import BaseClassifierTrainer, TrainingDataError
from mlb_app.ml.trainers.calibrated_logistic import CalibratedLogisticRegressionTrainer
from mlb_app.ml.trainers.hist_gradient_boosting import HistGradientBoostingTrainer
from mlb_app.ml.trainers.logistic import LogisticRegressionTrainer
from mlb_app.ml.trainers.random_forest import RandomForestTrainer


def tiny_features() -> list[dict[str, float]]:
    return [
        {"line": 0.5, "implied_probability": 0.40, "recent_rate": 0.20},
        {"line": 0.7, "implied_probability": 0.45, "recent_rate": 0.25},
        {"line": 1.0, "implied_probability": 0.48, "recent_rate": 0.35},
        {"line": 1.4, "implied_probability": 0.55, "recent_rate": 0.60},
        {"line": 1.6, "implied_probability": 0.58, "recent_rate": 0.70},
        {"line": 1.9, "implied_probability": 0.62, "recent_rate": 0.82},
    ]


def tiny_target() -> list[int]:
    return [0, 0, 0, 1, 1, 1]


@pytest.mark.parametrize(
    "trainer_cls",
    [
        LogisticRegressionTrainer,
        CalibratedLogisticRegressionTrainer,
        HistGradientBoostingTrainer,
        RandomForestTrainer,
    ],
)
def test_classifier_trainers_follow_probability_contract(trainer_cls: type[BaseClassifierTrainer]) -> None:
    trainer = trainer_cls(market="batter_total_bases")

    trainer.fit(tiny_features(), tiny_target())
    probabilities = trainer.predict_proba(tiny_features())
    metadata = trainer.get_metadata()

    assert probabilities.shape == (6, 2)
    assert ((probabilities >= 0.0) & (probabilities <= 1.0)).all()
    assert trainer.get_feature_names() == ["line", "implied_probability", "recent_rate"]
    assert metadata["market"] == "batter_total_bases"
    assert metadata["training_rows"] == 6
    assert metadata["positive_rows"] == 3
    assert metadata["positive_rate"] == 0.5
    assert metadata["dependency_versions"]["scikit-learn"] != "unavailable"


def test_logistic_trainer_can_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "logistic.joblib"
    trainer = LogisticRegressionTrainer(market="pitcher_strikeouts").fit(tiny_features(), tiny_target())

    trainer.save(path)
    loaded = LogisticRegressionTrainer.load(path)

    assert loaded.get_metadata()["model_name"] == "logistic_regression"
    assert loaded.get_feature_names() == trainer.get_feature_names()
    assert loaded.predict_proba(tiny_features()).shape == (6, 2)


def test_trainers_reject_single_class_targets_with_clear_error() -> None:
    trainer = LogisticRegressionTrainer(market="batter_hits")

    with pytest.raises(TrainingDataError, match="both positive and negative classes"):
        trainer.fit(tiny_features(), [1, 1, 1, 1, 1, 1])


def test_trainers_reject_leakage_feature_columns() -> None:
    rows = [dict(row, result=1) for row in tiny_features()]
    trainer = LogisticRegressionTrainer(market="batter_hits")

    with pytest.raises(ValueError, match="Blocked leakage fields"):
        trainer.fit(rows, tiny_target())
