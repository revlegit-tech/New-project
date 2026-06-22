from __future__ import annotations

from typing import Any

from mlb_app.ml.trainers.base import BaseClassifierTrainer, TrainingDataError, make_pipeline_classifier


class CalibratedLogisticRegressionTrainer(BaseClassifierTrainer):
    model_name = "calibrated_logistic_regression"
    calibrated = True

    def _build_estimator(self, y: Any) -> Any:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.linear_model import LogisticRegression

        np = _numpy()
        _, counts = np.unique(y, return_counts=True)
        minimum_class_count = int(counts.min()) if len(counts) else 0
        if minimum_class_count < 2:
            raise TrainingDataError("Calibrated logistic regression needs at least two rows in each class.")

        params = {
            "max_iter": 1000,
            "class_weight": "balanced",
            "solver": "lbfgs",
        }
        params.update(self.estimator_params)
        base = make_pipeline_classifier(LogisticRegression(**params), scale=True)
        cv = min(3, minimum_class_count)
        try:
            return CalibratedClassifierCV(estimator=base, cv=cv, method="sigmoid")
        except TypeError:
            return CalibratedClassifierCV(base_estimator=base, cv=cv, method="sigmoid")


def _numpy() -> Any:
    import numpy as np

    return np
