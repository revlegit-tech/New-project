from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


EPSILON = 1e-15


def binary_classification_metrics(y_true: Sequence[Any], y_probability: Sequence[Any]) -> dict[str, Any]:
    targets = [_target(value) for value in y_true]
    probabilities = [_probability(value) for value in y_probability]
    pairs = [(target, probability) for target, probability in zip(targets, probabilities) if target is not None and probability is not None]
    warnings: list[str] = []
    if not pairs:
        return {"rows": 0, "brierScore": None, "logLoss": None, "auc": None, "warnings": ["no valid predictions"]}

    y = [target for target, _probability_value in pairs]
    p = [probability for _target_value, probability in pairs]
    classes = set(y)
    if len(classes) < 2:
        warnings.append("single-class window; AUC is unavailable")

    return {
        "rows": len(pairs),
        "positiveRows": sum(1 for value in y if value == 1),
        "negativeRows": sum(1 for value in y if value == 0),
        "brierScore": round(sum((probability - target) ** 2 for target, probability in pairs) / len(pairs), 6),
        "logLoss": round(
            -sum(
                target * math.log(_clamp(probability)) + (1 - target) * math.log(1 - _clamp(probability))
                for target, probability in pairs
            )
            / len(pairs),
            6,
        ),
        "auc": round(_auc(y, p), 6) if len(classes) == 2 else None,
        "warnings": warnings,
    }


def _auc(y_true: Sequence[int], y_probability: Sequence[float]) -> float:
    positives = [score for target, score in zip(y_true, y_probability) if target == 1]
    negatives = [score for target, score in zip(y_true, y_probability) if target == 0]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def _target(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "hit", "win", "over", "yes"}:
        return 1
    if text in {"0", "false", "miss", "loss", "under", "no"}:
        return 0
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return 1 if number == 1 else 0 if number == 0 else None


def _probability(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1.0 and number <= 100.0:
        number /= 100.0
    if number < 0.0 or number > 1.0:
        return None
    return number


def _clamp(value: float) -> float:
    return min(max(float(value), EPSILON), 1.0 - EPSILON)
