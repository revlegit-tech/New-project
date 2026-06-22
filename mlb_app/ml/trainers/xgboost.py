from __future__ import annotations

from importlib.util import find_spec
from typing import Any

from mlb_app.ml.trainers.base import BaseClassifierTrainer, TrainerUnavailableError


class XGBoostClassifierTrainer(BaseClassifierTrainer):
    model_name = "xgboost_classifier"
    calibrated = False
    dependency_packages = ("scikit-learn", "numpy", "pandas", "joblib", "xgboost")

    def __init__(
        self,
        *,
        market: str = "",
        model_version: str = "v1",
        feature_names: list[str] | None = None,
        estimator_params: dict[str, Any] | None = None,
        use_scale_pos_weight: bool = False,
    ) -> None:
        super().__init__(
            market=market,
            model_version=model_version,
            feature_names=feature_names,
            estimator_params=estimator_params,
        )
        self.use_scale_pos_weight = bool(use_scale_pos_weight)

    @classmethod
    def is_available(cls) -> bool:
        return find_spec("xgboost") is not None

    def _build_estimator(self, y: Any) -> Any:
        try:
            from xgboost import XGBClassifier
        except ImportError as error:
            raise TrainerUnavailableError(
                "XGBoost is optional and is not installed. Install it with `pip install -r requirements-ml.txt` "
                "to use XGBoostClassifierTrainer."
            ) from error

        params: dict[str, Any] = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "tree_method": "hist",
            "n_estimators": 300,
            "max_depth": 3,
            "learning_rate": 0.03,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
            "reg_lambda": 2.0,
            "reg_alpha": 0.0,
            "min_child_weight": 10,
            "random_state": 42,
            "n_jobs": 4,
        }
        if self.use_scale_pos_weight:
            params["scale_pos_weight"] = _scale_pos_weight(y)
        params.update(self.estimator_params)
        return XGBClassifier(**params)


def _scale_pos_weight(y: Any) -> float:
    negative = int(sum(1 for value in y if int(value) == 0))
    positive = int(sum(1 for value in y if int(value) == 1))
    return float(negative / positive) if positive else 1.0
