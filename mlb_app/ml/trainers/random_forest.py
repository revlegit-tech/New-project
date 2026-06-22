from __future__ import annotations

from typing import Any

from mlb_app.ml.trainers.base import BaseClassifierTrainer, make_pipeline_classifier


class RandomForestTrainer(BaseClassifierTrainer):
    model_name = "random_forest_classifier"
    calibrated = False

    def _build_estimator(self, y: Any) -> Any:
        from sklearn.ensemble import RandomForestClassifier

        params = {
            "n_estimators": 250,
            "random_state": 42,
            "min_samples_leaf": 2,
            "class_weight": "balanced",
            "n_jobs": 1,
        }
        params.update(self.estimator_params)
        return make_pipeline_classifier(RandomForestClassifier(**params), scale=False)
