from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mlb_app.ml.trainers.base import ModelTrainer, TrainerNotFittedError, TrainingDataError


class ProbabilityEnsembleTrainer(ModelTrainer):
    """Extension point for later model blending without production promotion."""

    def __init__(self, members: Sequence[ModelTrainer] | None = None, weights: Sequence[float] | None = None) -> None:
        self.members = list(members or [])
        self.weights = list(weights or [])
        if self.weights and len(self.weights) != len(self.members):
            raise TrainingDataError("Ensemble weights must match the number of member trainers.")

    def fit(self, X: Any, y: Any, *, sample_weight: Any | None = None) -> "ProbabilityEnsembleTrainer":
        raise NotImplementedError("Ensemble fitting is intentionally not wired in this sprint.")

    def predict_proba(self, X: Any) -> Any:
        if not self.members:
            raise TrainerNotFittedError("Ensemble requires at least one fitted member trainer.")
        np = _numpy()
        probabilities = [member.predict_proba(X) for member in self.members]
        weights = self.weights or [1.0] * len(probabilities)
        return np.average(probabilities, axis=0, weights=weights)

    def save(self, path: str) -> Any:
        raise NotImplementedError("Ensemble artifact persistence is intentionally deferred.")

    @classmethod
    def load(cls, path: str) -> "ProbabilityEnsembleTrainer":
        raise NotImplementedError("Ensemble artifact loading is intentionally deferred.")

    def get_metadata(self) -> dict[str, Any]:
        return {
            "model_name": "probability_ensemble",
            "member_count": len(self.members),
            "production_ready": False,
        }

    def get_feature_names(self) -> list[str]:
        return self.members[0].get_feature_names() if self.members else []


def _numpy() -> Any:
    import numpy as np

    return np
