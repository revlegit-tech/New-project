from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_EDGE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("negative", float("-inf"), 0.0),
    ("0_to_2", 0.0, 0.02),
    ("2_to_5", 0.02, 0.05),
    ("5_to_10", 0.05, 0.10),
    ("10_plus", 0.10, float("inf")),
)


def roi_by_edge_bucket(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for name, lower, upper in DEFAULT_EDGE_BUCKETS:
        selected = [
            row
            for row in rows
            if (edge := _edge(row.get("edge") or row.get("edgePercent") or row.get("model_edge"))) is not None
            and edge >= lower
            and edge < upper
        ]
        profit = sum(_float(row.get("target_profit_1u") or row.get("profit_1u")) or 0.0 for row in selected)
        stake = len(selected)
        buckets.append(
            {
                "bucket": name,
                "lower": None if lower == float("-inf") else lower,
                "upper": None if upper == float("inf") else upper,
                "rows": stake,
                "profit1u": round(profit, 6),
                "roi": round(profit / stake, 6) if stake else None,
            }
        )
    return buckets


def _edge(value: Any) -> float | None:
    number = _float(value)
    if number is None:
        return None
    return number / 100.0 if abs(number) > 1.0 else number


def _float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
