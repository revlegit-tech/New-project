from __future__ import annotations

from typing import Any

from mlb_app.ml.trainers.base import BaseClassifierTrainer, make_pipeline_classifier


class HistGradientBoostingTrainer(BaseClassifierTrainer):
    model_name = "hist_gradient_boosting_classifier"
    calibrated = False

    def _build_estimator(self, y: Any) -> Any:
        from sklearn.ensemble import HistGradientBoostingClassifier

        params = {
            "max_iter": 100,
            "learning_rate": 0.05,
            "max_leaf_nodes": 15,
            "l2_regularization": 0.0,
            "random_state": 42,
        }
        params.update(self.estimator_params)
        return make_pipeline_classifier(HistGradientBoostingClassifier(**params), scale=False)
