from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from mlb_app.services.ml_feature_schema import blocked_feature_names, leakage_fields_in_payload

TARGET_PREFIX = "target_"
BLOCKED_FEATURE_FIELDS: frozenset[str] = frozenset(blocked_feature_names())
_BLOCKED_LOWER = frozenset(name.lower() for name in BLOCKED_FEATURE_FIELDS)


def blocked_ml_feature_fields() -> set[str]:
    return set(BLOCKED_FEATURE_FIELDS)


def is_blocked_feature_column(name: str, *, allow_target_prefixed: bool = False) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    if allow_target_prefixed and text.lower().startswith(TARGET_PREFIX):
        return False
    return text in BLOCKED_FEATURE_FIELDS or text.lower() in _BLOCKED_LOWER


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


def assert_no_leakage_payload(payload: Mapping[str, Any], *, allow_target_prefixed: bool = False) -> None:
    leaking = sorted(
        name
        for name in leakage_fields_in_payload(payload)
        if is_blocked_feature_column(name, allow_target_prefixed=allow_target_prefixed)
    )
    if leaking:
        raise ValueError(f"Blocked leakage fields are not allowed in model features: {', '.join(leaking)}")
