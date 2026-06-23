from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mlb_app.ml.evaluation.metrics import _probability, _target


def calibration_report(
    y_true: Sequence[Any],
    y_probability: Sequence[Any],
    *,
    bucket_count: int = 10,
) -> dict[str, Any]:
    pairs = [
        (target, probability)
        for target, probability in ((_target(target), _probability(probability)) for target, probability in zip(y_true, y_probability))
        if target is not None and probability is not None
    ]
    if not pairs:
        return {"bucketCount": 0, "buckets": [], "expectedCalibrationError": None, "warnings": ["no valid predictions"]}

    count = max(1, int(bucket_count))
    buckets: list[dict[str, Any]] = []
    ece = 0.0
    total = len(pairs)
    for index in range(count):
        lower = index / count
        upper = (index + 1) / count
        bucket_pairs = [
            (target, probability)
            for target, probability in pairs
            if probability >= lower and (probability < upper or (index == count - 1 and probability <= upper))
        ]
        rows = len(bucket_pairs)
        avg_prediction = sum(probability for _target_value, probability in bucket_pairs) / rows if rows else None
        hit_rate = sum(target for target, _probability_value in bucket_pairs) / rows if rows else None
        if rows and avg_prediction is not None and hit_rate is not None:
            ece += (rows / total) * abs(avg_prediction - hit_rate)
        buckets.append(
            {
                "bucket": index,
                "lower": round(lower, 6),
                "upper": round(upper, 6),
                "rows": rows,
                "avgPrediction": round(avg_prediction, 6) if avg_prediction is not None else None,
                "hitRate": round(hit_rate, 6) if hit_rate is not None else None,
            }
        )
    return {"bucketCount": count, "buckets": buckets, "expectedCalibrationError": round(ece, 6), "warnings": []}
