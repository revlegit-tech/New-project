from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.datasets.feature_matrix_builder import build_feature_matrix
from mlb_app.ml.datasets.leakage_guard import (
    assert_feature_columns_safe,
    assert_training_columns_prefixed,
    is_feature_column,
)
from mlb_app.ml.datasets.target_builder import build_binary_target
from mlb_app.ml.market_config import get_market_config, normalize_market
from mlb_app.ml.registry.artifact_writer import ArtifactWriteResult, ModelArtifactWriter
from mlb_app.ml.registry.metadata import utc_now_iso
from mlb_app.ml.trainers.base import ModelTrainer, TrainerUnavailableError, TrainingDataError
from mlb_app.ml.trainers.calibrated_logistic import CalibratedLogisticRegressionTrainer
from mlb_app.ml.trainers.hist_gradient_boosting import HistGradientBoostingTrainer
from mlb_app.ml.trainers.logistic import LogisticRegressionTrainer
from mlb_app.ml.trainers.random_forest import RandomForestTrainer
from mlb_app.ml.trainers.xgboost import XGBoostClassifierTrainer
from mlb_app.services.model_registry_service import (
    TRAINING_RUNNER_STATUSES,
    write_training_registry_entries,
)


@dataclass(frozen=True)
class ModelTrainAttempt:
    model_key: str
    status: str
    reason: str = ""
    artifact: ArtifactWriteResult | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "modelKey": self.model_key,
            "status": self.status,
            "reason": self.reason,
            "metrics": dict(self.metrics),
            "artifact": self.artifact.as_dict() if self.artifact else None,
        }


@dataclass(frozen=True)
class MarketTrainingResult:
    market: str
    status: str
    reason: str
    training_rows: int = 0
    positive_rows: int = 0
    negative_rows: int = 0
    feature_names: tuple[str, ...] = ()
    target_column: str = ""
    attempts: tuple[ModelTrainAttempt, ...] = ()

    @property
    def trained_artifacts(self) -> list[ArtifactWriteResult]:
        return [attempt.artifact for attempt in self.attempts if attempt.artifact is not None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "status": self.status,
            "reason": self.reason,
            "trainingRows": self.training_rows,
            "positiveRows": self.positive_rows,
            "negativeRows": self.negative_rows,
            "featureNames": list(self.feature_names),
            "targetColumn": self.target_column,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
        }


@dataclass(frozen=True)
class TrainingRunResult:
    status: str
    dry_run: bool
    training_path: str
    artifact_root: str
    registry_path: str
    markets: tuple[MarketTrainingResult, ...]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dryRun": self.dry_run,
            "trainingPath": self.training_path,
            "artifactRoot": self.artifact_root,
            "registryPath": self.registry_path,
            "markets": [market.as_dict() for market in self.markets],
            "warnings": list(self.warnings),
        }


class ModelTrainingService:
    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        artifact_writer: ModelArtifactWriter | None = None,
    ) -> None:
        self.settings = settings
        self.artifact_writer = artifact_writer or ModelArtifactWriter(settings.model_dir / "artifacts" / "sprint19")

    def train_from_dataset(
        self,
        *,
        training_path: str | Path,
        markets: Sequence[str] | None = None,
        model_keys: Sequence[str] | None = None,
        model_version: str | None = None,
        registry_status: str = "candidate",
        registry_path: str | Path | None = None,
        dry_run: bool = False,
        test_mode: bool = False,
        minimum_rows: int | None = None,
        minimum_positive_rows: int | None = None,
    ) -> TrainingRunResult:
        status = _validate_runner_status(registry_status)
        path = Path(training_path)
        rows = load_training_rows(path)
        if not rows:
            return TrainingRunResult(
                status="skipped",
                dry_run=dry_run,
                training_path=str(path),
                artifact_root=str(self.artifact_writer.artifact_root),
                registry_path=str(registry_path or self.settings.model_registry_path),
                markets=(),
                warnings=("training dataset is empty",),
            )
        _assert_dataset_contract(rows)
        selected_markets = tuple(normalize_market(market) for market in markets) if markets else _markets_from_rows(rows)
        version = model_version or f"sprint19-{utc_now_iso().replace(':', '').replace('-', '')}"
        results: list[MarketTrainingResult] = []
        registry_entries: list[dict[str, Any]] = []
        for market in selected_markets:
            result = self.train_market(
                rows,
                market=market,
                model_keys=model_keys,
                model_version=version,
                registry_status=status,
                dry_run=dry_run,
                test_mode=test_mode,
                minimum_rows=minimum_rows,
                minimum_positive_rows=minimum_positive_rows,
                source_dataset=str(path),
            )
            results.append(result)
            for artifact in result.trained_artifacts:
                registry_entries.append(artifact.registry_entry)

        target_registry = Path(registry_path) if registry_path is not None else self.settings.model_registry_path
        if registry_entries and not dry_run:
            write_training_registry_entries(target_registry, registry_entries, status=status)
        run_status = "trained" if any(result.status == "trained" for result in results) else "skipped"
        return TrainingRunResult(
            status=run_status,
            dry_run=dry_run,
            training_path=str(path),
            artifact_root=str(self.artifact_writer.artifact_root),
            registry_path=str(target_registry),
            markets=tuple(results),
        )

    def train_market(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        market: str,
        model_keys: Sequence[str] | None = None,
        model_version: str,
        registry_status: str,
        dry_run: bool,
        test_mode: bool,
        minimum_rows: int | None,
        minimum_positive_rows: int | None,
        source_dataset: str = "",
    ) -> MarketTrainingResult:
        market_key = normalize_market(market)
        config = get_market_config(market_key)
        market_rows = [dict(row) for row in rows if _row_market(row) == market_key]
        if not market_rows:
            return MarketTrainingResult(market=market_key, status="skipped", reason="no rows for market")

        frame = _pandas().DataFrame(market_rows)
        target = build_binary_target(frame, target_column="target_hit")
        frame = frame.loc[target.index]
        feature_matrix = build_feature_matrix(frame)
        feature_names = tuple(str(column) for column in feature_matrix.columns)
        assert_feature_columns_safe(feature_names)
        if not feature_names:
            return MarketTrainingResult(market=market_key, status="skipped", reason="no usable feature_* columns")

        positive_rows = int((target == 1).sum())
        negative_rows = int((target == 0).sum())
        training_rows = int(len(target))
        min_rows = int(minimum_rows if minimum_rows is not None else (4 if test_mode else config.minimum_training_rows))
        min_positive = int(
            minimum_positive_rows
            if minimum_positive_rows is not None
            else (2 if test_mode else config.minimum_positive_rows)
        )
        if training_rows < min_rows:
            return MarketTrainingResult(
                market=market_key,
                status="skipped",
                reason=f"fewer than {min_rows} training rows",
                training_rows=training_rows,
                positive_rows=positive_rows,
                negative_rows=negative_rows,
                feature_names=feature_names,
                target_column="target_hit",
            )
        if positive_rows == 0 or negative_rows == 0:
            return MarketTrainingResult(
                market=market_key,
                status="skipped",
                reason="training targets must contain both positive and negative classes",
                training_rows=training_rows,
                positive_rows=positive_rows,
                negative_rows=negative_rows,
                feature_names=feature_names,
                target_column="target_hit",
            )
        if positive_rows < min_positive:
            return MarketTrainingResult(
                market=market_key,
                status="skipped",
                reason=f"fewer than {min_positive} positive target rows",
                training_rows=training_rows,
                positive_rows=positive_rows,
                negative_rows=negative_rows,
                feature_names=feature_names,
                target_column="target_hit",
            )

        selected_models = tuple(model_keys or config.candidate_models)
        attempts: list[ModelTrainAttempt] = []
        for model_key in selected_models:
            attempts.append(
                self._train_model_attempt(
                    market=market_key,
                    model_key=str(model_key),
                    model_version=model_version,
                    registry_status=registry_status,
                    feature_matrix=feature_matrix,
                    target=target,
                    training_rows=training_rows,
                    positive_rows=positive_rows,
                    negative_rows=negative_rows,
                    dry_run=dry_run,
                    test_mode=test_mode,
                    source_dataset=source_dataset,
                )
            )
        trained = [attempt for attempt in attempts if attempt.status == "trained"]
        return MarketTrainingResult(
            market=market_key,
            status="trained" if trained else "skipped",
            reason="" if trained else "no supported candidate trainers produced an artifact",
            training_rows=training_rows,
            positive_rows=positive_rows,
            negative_rows=negative_rows,
            feature_names=feature_names,
            target_column="target_hit",
            attempts=tuple(attempts),
        )

    def _train_model_attempt(
        self,
        *,
        market: str,
        model_key: str,
        model_version: str,
        registry_status: str,
        feature_matrix: Any,
        target: Any,
        training_rows: int,
        positive_rows: int,
        negative_rows: int,
        dry_run: bool,
        test_mode: bool,
        source_dataset: str,
    ) -> ModelTrainAttempt:
        trainer_cls = _trainer_class(model_key)
        if trainer_cls is None:
            return ModelTrainAttempt(model_key=model_key, status="skipped", reason="unsupported trainer family")
        if trainer_cls is XGBoostClassifierTrainer and not XGBoostClassifierTrainer.is_available():
            return ModelTrainAttempt(model_key=model_key, status="skipped", reason="xgboost is not installed")
        trainer = trainer_cls(
            market=market,
            model_version=model_version,
            feature_names=list(feature_matrix.columns),
            estimator_params=_test_estimator_params(model_key) if test_mode else None,
        )
        try:
            trainer.fit(feature_matrix, target)
        except (ModuleNotFoundError, TrainerUnavailableError, TrainingDataError, ValueError) as error:
            return ModelTrainAttempt(model_key=model_key, status="skipped", reason=str(error))
        metrics = _in_sample_metrics(trainer, feature_matrix, target)
        if dry_run:
            return ModelTrainAttempt(model_key=model_key, status="trained", reason="dry run", metrics=metrics)
        artifact = self.artifact_writer.write(
            market=market,
            model_key=model_key,
            trainer=trainer,
            model_version=model_version,
            status=registry_status,
            training_rows=training_rows,
            positive_rows=positive_rows,
            negative_rows=negative_rows,
            target_column="target_hit",
            metrics=metrics,
            source_dataset=source_dataset,
        )
        return ModelTrainAttempt(model_key=model_key, status="trained", artifact=artifact, metrics=metrics)


def load_training_rows(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Training dataset not found: {target}")
    if target.suffix.lower() == ".json":
        payload = json.loads(target.read_text(encoding="utf-8"))
        raw_rows = payload.get("flat_rows") or payload.get("rows") if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            return []
        return [_flatten_training_row(row) for row in raw_rows if isinstance(row, Mapping)]
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _assert_dataset_contract(rows: Sequence[Mapping[str, Any]]) -> None:
    columns = tuple(dict.fromkeys(str(column) for row in rows for column in row))
    assert_training_columns_prefixed(columns)
    feature_columns = [column for column in columns if is_feature_column(column)]
    assert_feature_columns_safe(feature_columns)


def _flatten_training_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if any(str(key).startswith(("feature_", "target_", "meta_")) for key in row):
        return dict(row)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    features = row.get("features") if isinstance(row.get("features"), Mapping) else {}
    targets = row.get("targets") if isinstance(row.get("targets"), Mapping) else {}
    return {**dict(metadata), **dict(features), **dict(targets)}


def _markets_from_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(market for market in (_row_market(row) for row in rows) if market))


def _row_market(row: Mapping[str, Any]) -> str:
    return normalize_market(str(row.get("meta_market") or ""))


def _trainer_class(model_key: str) -> type[ModelTrainer] | None:
    key = normalize_market(model_key)
    return {
        "logistic": LogisticRegressionTrainer,
        "logistic_regression": LogisticRegressionTrainer,
        "calibrated_logistic": CalibratedLogisticRegressionTrainer,
        "calibrated_logistic_regression": CalibratedLogisticRegressionTrainer,
        "hist_gradient_boosting": HistGradientBoostingTrainer,
        "random_forest": RandomForestTrainer,
        "random_forest_classifier": RandomForestTrainer,
        "xgboost_classifier": XGBoostClassifierTrainer,
    }.get(key)


def _test_estimator_params(model_key: str) -> dict[str, Any]:
    key = normalize_market(model_key)
    if key in {"random_forest", "random_forest_classifier"}:
        return {"n_estimators": 10, "n_jobs": 1, "random_state": 42}
    if key == "hist_gradient_boosting":
        return {"max_iter": 10, "random_state": 42}
    if key == "xgboost_classifier":
        return {"n_estimators": 10, "n_jobs": 1, "random_state": 42}
    return {}


def _in_sample_metrics(trainer: ModelTrainer, feature_matrix: Any, target: Any) -> dict[str, Any]:
    probabilities = trainer.predict_proba(feature_matrix)[:, 1]
    y = list(int(value) for value in target)
    p = [float(value) for value in probabilities]
    metrics: dict[str, Any] = {"rows": len(y)}
    try:
        from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

        metrics["brierScore"] = round(float(brier_score_loss(y, p)), 6)
        metrics["logLoss"] = round(float(log_loss(y, p, labels=[0, 1])), 6)
        metrics["auc"] = round(float(roc_auc_score(y, p)), 6) if len(set(y)) == 2 else None
    except Exception:
        metrics["brierScore"] = None
        metrics["logLoss"] = None
        metrics["auc"] = None
    return metrics


def _validate_runner_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in TRAINING_RUNNER_STATUSES:
        raise ValueError("Training runner can only write candidate or shadow registry entries.")
    return status


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is required to train MLB models from Sprint 18 datasets.") from error
    return pd
