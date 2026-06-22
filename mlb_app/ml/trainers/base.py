from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from mlb_app.ml.datasets.leakage_guard import assert_feature_columns_safe
from mlb_app.ml.datasets.target_builder import normalize_binary_target

ARTIFACT_SCHEMA_VERSION = "mlb-model-artifact.v1"


class TrainingDataError(ValueError):
    """Raised when a trainer receives invalid training data."""


class TrainerNotFittedError(RuntimeError):
    """Raised when probabilities are requested before fit/load."""


class TrainerUnavailableError(RuntimeError):
    """Raised when an optional model dependency is unavailable."""


class ModelTrainer(ABC):
    @abstractmethod
    def fit(self, X: Any, y: Any, *, sample_weight: Any | None = None) -> "ModelTrainer":
        raise NotImplementedError

    @abstractmethod
    def predict_proba(self, X: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def save(self, path: str | Path) -> Path:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> "ModelTrainer":
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_feature_names(self) -> list[str]:
        raise NotImplementedError


class BaseClassifierTrainer(ModelTrainer):
    model_name = "base_classifier"
    calibrated = False
    dependency_packages: tuple[str, ...] = ("scikit-learn", "numpy", "pandas", "joblib")

    def __init__(
        self,
        *,
        market: str = "",
        model_version: str = "v1",
        feature_names: Sequence[str] | None = None,
        estimator_params: dict[str, Any] | None = None,
    ) -> None:
        self.market = str(market or "")
        self.model_version = str(model_version or "v1")
        self.feature_names = [str(name) for name in feature_names] if feature_names is not None else []
        self.estimator_params = dict(estimator_params or {})
        self._model: Any | None = None
        self._metadata: dict[str, Any] = {}

    def fit(self, X: Any, y: Any, *, sample_weight: Any | None = None) -> "BaseClassifierTrainer":
        frame = self._coerce_feature_frame(X, fit=True)
        target = self._coerce_target(y, expected_rows=len(frame))
        negative_rows, positive_rows = self._validate_binary_target(target)
        model = self._build_estimator(target)
        fit_kwargs = self._fit_kwargs(model, sample_weight)
        model.fit(frame, target, **fit_kwargs)
        self._model = model
        training_rows = int(len(target))
        self._metadata = {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "market": self.market,
            "feature_names": list(self.feature_names),
            "trained_at": _utc_now_label(),
            "training_rows": training_rows,
            "positive_rows": positive_rows,
            "negative_rows": negative_rows,
            "positive_rate": round(positive_rows / training_rows, 6) if training_rows else 0.0,
            "calibrated": bool(self.calibrated),
            "dependency_versions": self._dependency_versions(),
        }
        return self

    def predict_proba(self, X: Any) -> Any:
        self._require_model()
        frame = self._coerce_feature_frame(X, fit=False)
        return self._model.predict_proba(frame)

    def save(self, path: str | Path) -> Path:
        self._require_model()
        joblib = _joblib()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "trainer_class": f"{self.__class__.__module__}.{self.__class__.__name__}",
                "model": self._model,
                "metadata": self.get_metadata(),
                "feature_names": self.get_feature_names(),
            },
            target,
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> "BaseClassifierTrainer":
        joblib = _joblib()
        payload = joblib.load(Path(path))
        metadata = dict(payload.get("metadata") or {})
        trainer = cls(
            market=str(metadata.get("market") or ""),
            model_version=str(metadata.get("model_version") or "v1"),
            feature_names=list(payload.get("feature_names") or metadata.get("feature_names") or []),
        )
        trainer._model = payload.get("model")
        trainer._metadata = metadata
        return trainer

    def get_metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    def get_feature_names(self) -> list[str]:
        return list(self.feature_names)

    @abstractmethod
    def _build_estimator(self, y: Any) -> Any:
        raise NotImplementedError

    def _coerce_feature_frame(self, X: Any, *, fit: bool) -> Any:
        pd = _pandas()
        np = _numpy()
        if isinstance(X, pd.DataFrame):
            frame = X.copy()
        else:
            frame = pd.DataFrame(X)

        if frame.empty:
            raise TrainingDataError("Feature matrix must contain at least one row.")

        if fit:
            if self.feature_names:
                if len(frame.columns) == len(self.feature_names) and not set(self.feature_names).issubset(frame.columns):
                    frame.columns = list(self.feature_names)
                else:
                    frame = frame.reindex(columns=self.feature_names)
            else:
                self.feature_names = _column_names(frame)
                frame.columns = list(self.feature_names)
        else:
            if not self.feature_names:
                raise TrainerNotFittedError("Trainer has no fitted feature names.")
            if len(frame.columns) == len(self.feature_names) and not set(self.feature_names).issubset(frame.columns):
                frame.columns = list(self.feature_names)
            else:
                frame = frame.reindex(columns=self.feature_names)

        assert_feature_columns_safe(self.feature_names)
        if not self.feature_names:
            raise TrainingDataError("Feature matrix must contain at least one feature column.")
        frame = frame.apply(pd.to_numeric, errors="coerce")
        return frame.replace([np.inf, -np.inf], np.nan)

    def _coerce_target(self, y: Any, *, expected_rows: int) -> Any:
        pd = _pandas()
        target = pd.Series(list(y)).map(normalize_binary_target)
        if len(target) != expected_rows:
            raise TrainingDataError("Feature matrix and target must have the same row count.")
        if target.isna().any():
            raise TrainingDataError("Training targets must be binary 0/1 labels.")
        return target.astype(int).to_numpy()

    def _validate_binary_target(self, target: Any) -> tuple[int, int]:
        np = _numpy()
        values, counts = np.unique(target, return_counts=True)
        count_by_class = {int(value): int(count) for value, count in zip(values, counts, strict=False)}
        positive_rows = int(count_by_class.get(1, 0))
        negative_rows = int(count_by_class.get(0, 0))
        if positive_rows == 0 or negative_rows == 0:
            raise TrainingDataError("Training targets must contain both positive and negative classes.")
        return negative_rows, positive_rows

    def _fit_kwargs(self, model: Any, sample_weight: Any | None) -> dict[str, Any]:
        if sample_weight is None:
            return {}
        if hasattr(model, "steps"):
            return {"model__sample_weight": sample_weight}
        return {"sample_weight": sample_weight}

    def _require_model(self) -> None:
        if self._model is None:
            raise TrainerNotFittedError("Trainer must be fit or loaded before calling predict_proba.")

    def _dependency_versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        for package in self.dependency_packages:
            try:
                versions[package] = version(package)
            except PackageNotFoundError:
                versions[package] = "unavailable"
        return versions


def make_pipeline_classifier(model: Any, *, scale: bool = False) -> Any:
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        steps.append(("scale", StandardScaler()))
    steps.append(("model", model))
    return Pipeline(steps=steps)


def _column_names(frame: Any) -> list[str]:
    names: list[str] = []
    for index, column in enumerate(frame.columns):
        text = str(column)
        if text.isdigit() or text.startswith("Unnamed:"):
            text = f"feature_{index}"
        names.append(text)
    return names


def _utc_now_label() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _joblib() -> Any:
    try:
        import joblib
    except ImportError as error:
        raise TrainerUnavailableError("joblib is required to save and load MLB model artifacts.") from error
    return joblib


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as error:
        raise TrainerUnavailableError("numpy is required for MLB model trainers.") from error
    return np


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise TrainerUnavailableError("pandas is required for MLB model trainers.") from error
    return pd
