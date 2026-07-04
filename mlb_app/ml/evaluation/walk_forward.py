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
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in ordered:
        rows_by_date.setdefault(str(row.get(date_field) or ""), []).append(row)
    dates = sorted(rows_by_date)
    splits: list[WalkForwardSplit] = []
    step = max(1, int(validation_window))
    first_validation_index: int | None = None
    for date_index in range(1, len(dates)):
        train_row_count = sum(len(rows_by_date[date]) for date in dates[:date_index])
        if train_row_count >= min_train_rows:
            first_validation_index = date_index
            break
    if first_validation_index is None:
        return []
    for date_index in range(first_validation_index, len(dates), step):
        validation_start_date = dates[date_index]
        train_dates = dates[:date_index]
        train = tuple(row for date in train_dates for row in rows_by_date[date])
        validation_dates = dates[date_index : date_index + step]
        validation = tuple(row for date in validation_dates for row in rows_by_date[date])
        if not validation:
            continue
        splits.append(
            WalkForwardSplit(
                train_rows=train,
                validation_rows=validation,
                train_end_date=str(train[-1].get(date_field) or ""),
                validation_start_date=validation_start_date,
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
                "validationDates": sorted({str(row.get(date_field) or "") for row in split.validation_rows if str(row.get(date_field) or "")}),
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


def evaluate_training_rows_by_market(
    rows: Sequence[Mapping[str, Any]],
    *,
    markets: Sequence[str] | None = None,
    date_field: str = "meta_game_date",
    market_field: str = "meta_market",
    target_field: str = "target_hit",
    min_train_rows: int = 300,
    validation_window: int = 20,
) -> dict[str, Any]:
    """Walk-forward evaluate normalized training rows by fitting only pregame feature columns."""

    if not rows:
        return {"status": "degraded", "markets": {}, "summary": {}, "warnings": ["empty dataset"]}
    feature_names = sorted({str(key) for row in rows for key in row.keys() if str(key).startswith("feature_")})
    assert_clv_not_in_features(feature_names)
    assert_feature_columns_safe(feature_names)
    if not feature_names:
        return {"status": "degraded", "markets": {}, "summary": {}, "warnings": ["no feature_* columns found"]}

    requested = {str(market).strip() for market in markets or [] if str(market).strip()}
    market_values = sorted(
        requested
        or {
            str(row.get(market_field) or "").strip()
            for row in rows
            if str(row.get(market_field) or "").strip()
        }
    )
    market_reports: dict[str, Any] = {}
    warnings: list[str] = []
    for market in market_values:
        market_rows = [dict(row) for row in rows if str(row.get(market_field) or "").strip() == market]
        if not market_rows:
            market_reports[market] = _empty_market_report(market, [f"no rows found for market {market}"])
            continue
        report = evaluate_walk_forward(
            market_rows,
            probability_fn=lambda train, validation, features=tuple(feature_names): _calibrated_logistic_probabilities(
                train,
                validation,
                features,
                target_field=target_field,
            ),
            date_field=date_field,
            target_field=target_field,
            min_train_rows=min_train_rows,
            validation_window=validation_window,
        )
        market_reports[market] = _market_report(market, report)
        warnings.extend(f"{market}: {warning}" for warning in report.get("warnings") or [])

    evaluated_rows = sum(int(report.get("metrics", {}).get("evaluatedRows") or 0) for report in market_reports.values())
    return {
        "status": "ok" if evaluated_rows else "degraded",
        "modelStage": "shadow",
        "modelKey": "calibrated_logistic",
        "markets": market_reports,
        "summary": {
            "marketCount": len(market_reports),
            "evaluatedRows": evaluated_rows,
            "readyMarkets": sorted(
                market for market, report in market_reports.items() if int(report.get("metrics", {}).get("evaluatedRows") or 0) > 0
            ),
        },
        "warnings": _dedupe(warnings),
    }


def _calibrated_logistic_probabilities(
    train_rows: Sequence[Mapping[str, Any]],
    validation_rows: Sequence[Mapping[str, Any]],
    feature_names: Sequence[str],
    *,
    target_field: str,
) -> list[float | None]:
    y_train = [_target01(row.get(target_field)) for row in train_rows]
    valid_train = [(row, target) for row, target in zip(train_rows, y_train, strict=False) if target is not None]
    if len({target for _row, target in valid_train}) < 2:
        return [None for _row in validation_rows]
    try:
        import numpy as np
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        x_train = np.asarray([[_float_for_model(row.get(feature)) for feature in feature_names] for row, _target in valid_train], dtype=float)
        y = np.asarray([target for _row, target in valid_train], dtype=int)
        x_validation = np.asarray([[_float_for_model(row.get(feature)) for feature in feature_names] for row in validation_rows], dtype=float)
        estimator = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=19),
        )
        min_class_count = min(int((y == 0).sum()), int((y == 1).sum()))
        if min_class_count >= 2:
            try:
                model = CalibratedClassifierCV(estimator=estimator, method="sigmoid", cv=min(3, min_class_count))
            except TypeError:  # pragma: no cover - older scikit-learn compatibility
                model = CalibratedClassifierCV(base_estimator=estimator, method="sigmoid", cv=min(3, min_class_count))
        else:
            model = estimator
        model.fit(x_train, y)
        probabilities = model.predict_proba(x_validation)[:, 1]
        return [max(0.0, min(1.0, float(probability))) for probability in probabilities]
    except Exception:
        return [None for _row in validation_rows]


def _market_report(market: str, report: dict[str, Any]) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    calibration = dict(summary.get("calibration") or {})
    metrics = {
        "evaluatedRows": int(summary.get("rows") or 0),
        "brierScore": summary.get("brierScore"),
        "logLoss": summary.get("logLoss"),
        "auc": summary.get("auc"),
        "positiveRows": int(summary.get("positiveRows") or 0),
        "negativeRows": int(summary.get("negativeRows") or 0),
        "validationDates": _validation_dates(report),
        "splitCount": len(report.get("splits") or []),
        "warnings": list(report.get("warnings") or []),
    }
    return {
        "market": market,
        "modelStage": "shadow",
        "modelKey": "calibrated_logistic",
        "metrics": metrics,
        "calibration": {
            "sampleCount": metrics["evaluatedRows"],
            "brierScore": metrics["brierScore"],
            "logLoss": metrics["logLoss"],
            "expectedCalibrationError": calibration.get("expectedCalibrationError"),
            "bucketCount": calibration.get("bucketCount") or 0,
            "buckets": calibration.get("buckets") or [],
        },
        "splits": report.get("splits") or [],
        "warnings": list(report.get("warnings") or []),
    }


def _empty_market_report(market: str, warnings: list[str]) -> dict[str, Any]:
    return {
        "market": market,
        "modelStage": "shadow",
        "modelKey": "calibrated_logistic",
        "metrics": {
            "evaluatedRows": 0,
            "brierScore": None,
            "logLoss": None,
            "auc": None,
            "positiveRows": 0,
            "negativeRows": 0,
            "validationDates": [],
            "splitCount": 0,
            "warnings": warnings,
        },
        "calibration": {
            "sampleCount": 0,
            "brierScore": None,
            "logLoss": None,
            "expectedCalibrationError": None,
            "bucketCount": 0,
            "buckets": [],
        },
        "splits": [],
        "warnings": warnings,
    }


def _validation_dates(report: dict[str, Any]) -> list[str]:
    dates: set[str] = set()
    for split in report.get("splits") or []:
        for value in split.get("validationDates") or []:
            date = str(value or "")
            if date:
                dates.add(date)
        if not split.get("validationDates"):
            start = str(split.get("validationStartDate") or "")
            end = str(split.get("validationEndDate") or "")
            if start:
                dates.add(start)
            if end:
                dates.add(end)
    return sorted(dates)


def _target01(value: Any) -> int | None:
    text = str(value if value is not None else "").strip().lower()
    if text in {"1", "true", "hit", "win", "over", "yes"}:
        return 1
    if text in {"0", "false", "miss", "loss", "under", "no"}:
        return 0
    return None


def _float_for_model(value: Any) -> float:
    try:
        text = str(value if value is not None else "").strip()
        if not text:
            return 0.0
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(items: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
