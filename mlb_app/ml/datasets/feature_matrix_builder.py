from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from mlb_app.ml.datasets.leakage_guard import assert_feature_columns_safe

DEFAULT_EXCLUDED_COLUMNS: frozenset[str] = frozenset(
    {
        "training_schema_version",
        "training_join_key",
        "feature_schema_version",
        "exported_at",
        "source",
        "source_row_id",
        "prop_key",
        "date",
        "player",
        "team",
        "opponent",
        "market",
        "side",
        "book",
    }
)


def build_feature_matrix(
    rows: Sequence[Mapping[str, Any]] | Any,
    *,
    feature_names: Sequence[str] | None = None,
    exclude_columns: Iterable[str] | None = None,
    numeric_only: bool = True,
) -> Any:
    pd = _pandas()
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame([dict(row) for row in rows])
    excluded = set(DEFAULT_EXCLUDED_COLUMNS)
    if exclude_columns is not None:
        excluded.update(str(column) for column in exclude_columns)

    if feature_names is None:
        selected = [
            str(column)
            for column in frame.columns
            if str(column) not in excluded and not str(column).lower().startswith("target_")
        ]
    else:
        selected = [str(column) for column in feature_names]

    assert_feature_columns_safe(selected)
    matrix = frame.reindex(columns=selected)
    if numeric_only:
        matrix = matrix.apply(pd.to_numeric, errors="coerce")
        matrix = matrix.dropna(axis=1, how="all")
        assert_feature_columns_safe(matrix.columns)
    return matrix


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is required to build MLB ML feature matrices.") from error
    return pd
