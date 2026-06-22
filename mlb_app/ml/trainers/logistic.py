from __future__ import annotations

from typing import Any

from mlb_app.ml.trainers.base import BaseClassifierTrainer, make_pipeline_classifier


class LogisticRegressionTrainer(BaseClassifierTrainer):
    model_name = "logistic_regression"
    calibrated = False

    def _build_estimator(self, y: Any) -> Any:
        from sklearn.linear_model import LogisticRegression

        params = {
            "max_iter": 1000,
            "class_weight": "balanced",
            "solver": "lbfgs",
        }
        params.update(self.estimator_params)
        return make_pipeline_classifier(LogisticRegression(**params), scale=True)
