from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mlb_app.ml.datasets.leakage_guard import assert_feature_columns_safe
from mlb_app.ml.evaluation.calibration import calibration_report
from mlb_app.ml.evaluation.clv import assert_clv_not_in_features, average_clv
from mlb_app.ml.evaluation.metrics import binary_classification_metrics
from mlb_app.ml.evaluation.roi import roi_by_edge_bucket


@dataclass(frozen=True)
class WalkForwardSplit:
    train_rows: tuple[dict[str, Any], ...]
    validation_rows: tuple[dict[str, Any], ...]
    train_end_date: str
    validation_start_date: str
    validation_end_date: str


def date_ordered_splits(
    rows: Sequence[Mapping[str, Any]],
    *,
    date_field: str = "meta_game_date",
    min_train_rows: int = 20,
    validation_window: int = 20,
) -> list[WalkForwardSplit]:
    ordered = sorted((dict(row) for row in rows if str(row.get(date_field) or "").strip()), key=lambda row: str(row.get(date_field) or ""))
    if len(ordered) <= min_train_rows:
        return []
    splits: list[WalkForwardSplit] = []
    step = max(1, int(validation_window))
    for start in range(max(1, int(min_train_rows)), len(ordered), step):
        train = tuple(ordered[:start])
        validation = tuple(ordered[start : start + step])
        if not validation:
            continue
        splits.append(
            WalkForwardSplit(
                train_rows=train,
                validation_rows=validation,
                train_end_date=str(train[-1].get(date_field) or ""),
                validation_start_date=str(validation[0].get(date_field) or ""),
                validation_end_date=str(validation[-1].get(date_field) or ""),
            )
        )
    return splits


def evaluate_walk_forward(
    rows: Sequence[Mapping[str, Any]],
    *,
    probability_fn: Callable[[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]], Sequence[Any]] | None = None,
    date_field: str = "meta_game_date",
    target_field: str = "target_hit",
    probability_field: str = "model_probability",
    min_train_rows: int = 20,
    validation_window: int = 20,
) -> dict[str, Any]:
    warnings: list[str] = []
    if not rows:
        return {"status": "degraded", "splits": [], "summary": {}, "warnings": ["empty dataset"]}

    feature_names = [str(key) for key in rows[0].keys() if str(key).startswith("feature_")]
    assert_clv_not_in_features(feature_names)
    assert_feature_columns_safe(feature_names)

    splits = date_ordered_splits(rows, date_field=date_field, min_train_rows=min_train_rows, validation_window=validation_window)
    if not splits:
        return {"status": "degraded", "splits": [], "summary": {}, "warnings": ["not enough dated rows for walk-forward evaluation"]}

    evaluated_rows: list[dict[str, Any]] = []
    split_reports: list[dict[str, Any]] = []
    for index, split in enumerate(splits):
        probabilities = (
            list(probability_fn(split.train_rows, split.validation_rows))
            if probability_fn is not None
            else [row.get(probability_field) for row in split.validation_rows]
        )
        targets = [row.get(target_field) for row in split.validation_rows]
        metrics = binary_classification_metrics(targets, probabilities)
        warnings.extend(metrics.get("warnings") or [])
        for row, probability in zip(split.validation_rows, probabilities):
            scored = dict(row)
            scored["model_probability"] = probability
            evaluated_rows.append(scored)
        split_reports.append(
            {
                "index": index,
                "trainRows": len(split.train_rows),
                "validationRows": len(split.validation_rows),
                "trainEndDate": split.train_end_date,
                "validationStartDate": split.validation_start_date,
                "validationEndDate": split.validation_end_date,
                "metrics": metrics,
            }
        )

    summary = binary_classification_metrics(
        [row.get(target_field) for row in evaluated_rows],
        [row.get("model_probability") for row in evaluated_rows],
    )
    return {
        "status": "ok",
        "splits": split_reports,
        "summary": {
            **summary,
            "calibration": calibration_report(
                [row.get(target_field) for row in evaluated_rows],
                [row.get("model_probability") for row in evaluated_rows],
            ),
            "roiByEdgeBucket": roi_by_edge_bucket(evaluated_rows),
            "clv": average_clv(evaluated_rows),
        },
        "warnings": _dedupe(warnings + list(summary.get("warnings") or [])),
    }


def _dedupe(items: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
