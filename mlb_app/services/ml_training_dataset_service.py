from __future__ import annotations

from mlb_app.services.backtest_dataset_builder_service import (
    BacktestDatasetBuilderService,
    TrainingBuildResult,
)


class MLTrainingDatasetService(BacktestDatasetBuilderService):
    """Compatibility name for the Sprint 18 prefixed ML training dataset builder."""


__all__ = ["MLTrainingDatasetService", "TrainingBuildResult"]
