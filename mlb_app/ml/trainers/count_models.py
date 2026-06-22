from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CountProjectionTrainer(ABC):
    """Skeleton for future count/projection models such as strikeout or total-base means."""

    model_name = "count_projection"

    @abstractmethod
    def fit(self, X: Any, y: Any, *, sample_weight: Any | None = None) -> "CountProjectionTrainer":
        raise NotImplementedError

    @abstractmethod
    def predict_expected_count(self, X: Any) -> Any:
        raise NotImplementedError

    def get_metadata(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "production_ready": False,
            "status": "skeleton",
        }


class PoissonProjectionTrainer(CountProjectionTrainer):
    model_name = "poisson_projection"

    def fit(self, X: Any, y: Any, *, sample_weight: Any | None = None) -> "PoissonProjectionTrainer":
        raise NotImplementedError("Poisson projection training is a future extension point.")

    def predict_expected_count(self, X: Any) -> Any:
        raise NotImplementedError("Poisson projection prediction is a future extension point.")


class NegativeBinomialProjectionTrainer(CountProjectionTrainer):
    model_name = "negative_binomial_projection"

    def fit(self, X: Any, y: Any, *, sample_weight: Any | None = None) -> "NegativeBinomialProjectionTrainer":
        raise NotImplementedError("Negative-binomial projection training is a future extension point.")

    def predict_expected_count(self, X: Any) -> Any:
        raise NotImplementedError("Negative-binomial projection prediction is a future extension point.")


class FutureXGBoostRegressorTrainer(CountProjectionTrainer):
    model_name = "xgboost_count_regressor"

    def fit(self, X: Any, y: Any, *, sample_weight: Any | None = None) -> "FutureXGBoostRegressorTrainer":
        raise NotImplementedError("XGBoost regressor training is intentionally deferred.")

    def predict_expected_count(self, X: Any) -> Any:
        raise NotImplementedError("XGBoost regressor prediction is intentionally deferred.")
