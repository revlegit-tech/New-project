from __future__ import annotations

from typing import Any


def chronological_train_test_split(
    frame: Any,
    target: Any,
    *,
    date_column: str = "date",
    test_size: float = 0.2,
) -> tuple[Any, Any, Any, Any]:
    pd = _pandas()
    if len(frame) != len(target):
        raise ValueError("Feature matrix and target must have the same row count.")
    if not 0.0 < float(test_size) < 1.0:
        raise ValueError("test_size must be between 0 and 1.")

    work = frame.copy()
    work["__target"] = list(target)
    if date_column in work.columns:
        work = work.sort_values(date_column, kind="mergesort")
    n_rows = len(work)
    n_test = max(1, int(round(n_rows * float(test_size))))
    n_train = max(1, n_rows - n_test)
    if n_train >= n_rows:
        n_train = n_rows - 1
    train = work.iloc[:n_train].copy()
    test = work.iloc[n_train:].copy()
    return (
        train.drop(columns=["__target"]),
        test.drop(columns=["__target"]),
        pd.Series(train["__target"].to_numpy(), index=train.index),
        pd.Series(test["__target"].to_numpy(), index=test.index),
    )


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is required for MLB ML train/test splitting.") from error
    return pd
