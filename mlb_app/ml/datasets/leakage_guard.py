from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from mlb_app.services.ml_feature_schema import blocked_feature_names, leakage_fields_in_payload

FEATURE_PREFIX = "feature_"
TARGET_PREFIX = "target_"
META_PREFIX = "meta_"
ALLOWED_TRAINING_PREFIXES: tuple[str, ...] = (FEATURE_PREFIX, TARGET_PREFIX, META_PREFIX)
BLOCKED_FEATURE_FIELDS: frozenset[str] = frozenset(blocked_feature_names())
_BLOCKED_LOWER = frozenset(name.lower() for name in BLOCKED_FEATURE_FIELDS)


def blocked_ml_feature_fields() -> set[str]:
    return set(BLOCKED_FEATURE_FIELDS)


def allowed_training_prefixes() -> tuple[str, ...]:
    return ALLOWED_TRAINING_PREFIXES


def is_feature_column(name: str) -> bool:
    return str(name or "").strip().lower().startswith(FEATURE_PREFIX)


def is_target_column(name: str) -> bool:
    return str(name or "").strip().lower().startswith(TARGET_PREFIX)


def is_meta_column(name: str) -> bool:
    return str(name or "").strip().lower().startswith(META_PREFIX)


def is_prefixed_training_column(name: str) -> bool:
    text = str(name or "").strip().lower()
    return bool(text and text.startswith(ALLOWED_TRAINING_PREFIXES))


def is_blocked_feature_column(name: str, *, allow_target_prefixed: bool = False) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if allow_target_prefixed and lowered.startswith(TARGET_PREFIX):
        return False
    if lowered.startswith(FEATURE_PREFIX):
        base = text[len(FEATURE_PREFIX) :]
        return base in BLOCKED_FEATURE_FIELDS or base.lower() in _BLOCKED_LOWER
    return text in BLOCKED_FEATURE_FIELDS or lowered in _BLOCKED_LOWER


def find_leakage_columns(columns: Iterable[str], *, allow_target_prefixed: bool = False) -> list[str]:
    leaks: list[str] = []
    for column in columns:
        text = str(column)
        if is_blocked_feature_column(text, allow_target_prefixed=allow_target_prefixed):
            leaks.append(text)
    return sorted(dict.fromkeys(leaks))


def assert_no_leakage_columns(columns: Iterable[str], *, allow_target_prefixed: bool = False) -> None:
    leaks = find_leakage_columns(columns, allow_target_prefixed=allow_target_prefixed)
    if leaks:
        raise ValueError(f"Blocked leakage fields are not allowed in model features: {', '.join(leaks)}")


def find_target_prefixed_feature_columns(columns: Iterable[str]) -> list[str]:
    return sorted(
        dict.fromkeys(str(column) for column in columns if str(column or "").strip().lower().startswith(TARGET_PREFIX))
    )


def assert_no_target_columns(columns: Iterable[str]) -> None:
    leaks = find_target_prefixed_feature_columns(columns)
    if leaks:
        raise ValueError(f"Target-prefixed columns are not allowed in model features: {', '.join(leaks)}")


def assert_feature_columns_safe(columns: Iterable[str]) -> None:
    assert_no_leakage_columns(columns, allow_target_prefixed=False)
    assert_no_target_columns(columns)


def find_unprefixed_training_columns(columns: Iterable[str]) -> list[str]:
    return sorted(
        dict.fromkeys(
            str(column)
            for column in columns
            if str(column or "").strip() and not is_prefixed_training_column(str(column))
        )
    )


def assert_training_columns_prefixed(columns: Iterable[str]) -> None:
    unprefixed = find_unprefixed_training_columns(columns)
    if unprefixed:
        raise ValueError(
            "Training dataset columns must use feature_, target_, or meta_ prefixes: "
            + ", ".join(unprefixed)
        )


def assert_training_row_contract(row: Mapping[str, Any]) -> None:
    assert_training_columns_prefixed(row.keys())
    assert_no_leakage_columns((key for key in row if is_feature_column(str(key))), allow_target_prefixed=False)


def split_training_row(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    assert_training_row_contract(row)
    return {
        "features": {str(key): value for key, value in row.items() if is_feature_column(str(key))},
        "targets": {str(key): value for key, value in row.items() if is_target_column(str(key))},
        "metadata": {str(key): value for key, value in row.items() if is_meta_column(str(key))},
    }


def assert_no_leakage_payload(payload: Mapping[str, Any], *, allow_target_prefixed: bool = False) -> None:
    leaking = sorted(
        name
        for name in leakage_fields_in_payload(payload)
        if is_blocked_feature_column(name, allow_target_prefixed=allow_target_prefixed)
    )
    if leaking:
        raise ValueError(f"Blocked leakage fields are not allowed in model features: {', '.join(leaking)}")
