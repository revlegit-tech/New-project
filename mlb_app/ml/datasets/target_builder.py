from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

TARGET_CANDIDATES: tuple[str, ...] = (
    "target_hit",
    "target_result",
    "target",
    "label",
    "over",
    "hit",
    "result",
)

POSITIVE_VALUES = {"1", "true", "yes", "y", "over", "hit", "win", "won", "graded_win"}
NEGATIVE_VALUES = {"0", "false", "no", "n", "under", "miss", "loss", "lost", "graded_loss"}


def build_binary_target(rows: Sequence[Mapping[str, Any]] | Any, *, target_column: str | None = None) -> Any:
    pd = _pandas()
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame([dict(row) for row in rows])
    selected = target_column or _first_existing_column(frame, TARGET_CANDIDATES)
    if not selected:
        raise ValueError(f"No binary target column found. Tried: {', '.join(TARGET_CANDIDATES)}")

    target = frame[selected].map(normalize_binary_target)
    valid = target.notna()
    if not bool(valid.any()):
        raise ValueError(f"Target column {selected!r} has no usable binary labels.")
    return target.loc[valid].astype(int)


def normalize_binary_target(value: Any) -> int | None:
    text = str(value).strip().lower()
    if text in POSITIVE_VALUES:
        return 1
    if text in NEGATIVE_VALUES:
        return 0
    try:
        return 1 if float(text) >= 1.0 else 0
    except (TypeError, ValueError):
        return None


def _first_existing_column(frame: Any, candidates: Sequence[str]) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return ""


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is required to build MLB ML targets.") from error
    return pd
