from __future__ import annotations

import importlib
import sys

import pytest

from mlb_app.ml.trainers.base import TrainerUnavailableError
from mlb_app.ml.trainers.xgboost import XGBoostClassifierTrainer


def tiny_features() -> list[dict[str, float]]:
    return [
        {"line": 0.5, "implied_probability": 0.40, "recent_rate": 0.20},
        {"line": 0.7, "implied_probability": 0.45, "recent_rate": 0.25},
        {"line": 1.0, "implied_probability": 0.48, "recent_rate": 0.35},
        {"line": 1.4, "implied_probability": 0.55, "recent_rate": 0.60},
        {"line": 1.6, "implied_probability": 0.58, "recent_rate": 0.70},
        {"line": 1.9, "implied_probability": 0.62, "recent_rate": 0.82},
    ]


def test_xgboost_trainer_is_optional() -> None:
    trainer = XGBoostClassifierTrainer(market="batter_total_bases", estimator_params={"n_estimators": 5, "n_jobs": 1})

    if not XGBoostClassifierTrainer.is_available():
        with pytest.raises(TrainerUnavailableError, match="XGBoost is optional"):
            trainer.fit(tiny_features(), [0, 0, 0, 1, 1, 1])
        return

    trainer.fit(tiny_features(), [0, 0, 0, 1, 1, 1])
    assert trainer.predict_proba(tiny_features()).shape == (6, 2)


def test_asgi_import_does_not_require_xgboost() -> None:
    sys.modules.pop("xgboost", None)

    module = importlib.import_module("mlb_app.asgi")

    assert hasattr(module, "app")
    assert "xgboost" not in sys.modules
