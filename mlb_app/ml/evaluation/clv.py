from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


CLV_FIELDS = ("closing_line_value", "target_closing_line_value", "clv", "target_clv")


def average_clv(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    for row in rows:
        for field in CLV_FIELDS:
            number = _float(row.get(field))
            if number is not None:
                values.append(number)
                break
    if not values:
        return {"available": False, "rows": 0, "averageClv": None, "warnings": ["CLV not available"]}
    return {"available": True, "rows": len(values), "averageClv": round(sum(values) / len(values), 6), "warnings": []}


def assert_clv_not_in_features(feature_names: Sequence[str]) -> None:
    leaking = [name for name in feature_names if "closing_line_value" in str(name).lower() or str(name).lower() in {"feature_clv"}]
    if leaking:
        raise ValueError("CLV is evaluation-only and cannot be used as a model feature: " + ", ".join(leaking))


def _float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
