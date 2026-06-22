from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from mlb_app.ml.market_config import feature_fields_for_market, get_market_config
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


def feature_names_for_market(
    market: str,
    *,
    available_columns: Iterable[str] | None = None,
) -> list[str]:
    configured = list(feature_fields_for_market(market))
    if available_columns is None:
        selected = configured
    else:
        available = {str(column) for column in available_columns}
        selected = [name for name in configured if name in available]
    assert_feature_columns_safe(selected)
    return selected


def build_market_feature_matrix(
    rows: Sequence[Mapping[str, Any]] | Any,
    *,
    market: str,
    numeric_only: bool = True,
    require_configured_features: bool = False,
) -> Any:
    pd = _pandas()
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame([dict(row) for row in rows])
    get_market_config(market)
    selected = feature_names_for_market(market, available_columns=frame.columns)
    if require_configured_features and not selected:
        raise ValueError(f"No configured feature columns are present for market {market!r}.")
    return build_feature_matrix(frame, feature_names=selected, numeric_only=numeric_only)


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is required to build MLB ML feature matrices.") from error
    return pd
