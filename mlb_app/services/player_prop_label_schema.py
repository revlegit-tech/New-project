from __future__ import annotations

from collections.abc import Mapping
from typing import Any

LABEL_SCHEMA_VERSION = "player-prop-labels.sprint13d.v1"

LABEL_FIELDS: tuple[str, ...] = (
    "label_schema_version",
    "graded_at",
    "date",
    "season",
    "source_row_id",
    "prop_key",
    "player",
    "team",
    "opponent",
    "market",
    "side",
    "line",
    "actual_value",
    "result",
    "hit",
    "push",
    "void",
    "label_status",
    "label_reason",
    "stat_source",
    "stat_key",
)

SUPPORTED_RESULTS: frozenset[str] = frozenset({"win", "loss", "push", "void", "ungraded"})
SUPPORTED_LABEL_STATUSES: frozenset[str] = frozenset(
    {
        "graded",
        "missing_stat",
        "missing_player",
        "missing_market_mapping",
        "invalid_line",
        "unsupported_market",
        "game_not_final",
        "ambiguous_match",
        "void",
    }
)

FEATURE_SAFE_LABEL_ID_FIELDS: frozenset[str] = frozenset(
    {
        "date",
        "season",
        "source_row_id",
        "prop_key",
        "player",
        "team",
        "opponent",
        "market",
        "side",
        "line",
    }
)

LABEL_ONLY_FIELDS: frozenset[str] = frozenset(LABEL_FIELDS) - FEATURE_SAFE_LABEL_ID_FIELDS


def normalize_result(result: Any = "", *, hit: Any = None, push: Any = None, void: Any = None) -> str:
    if _truthy(void):
        return "void"
    if _truthy(push):
        return "push"
    if hit is not None:
        if _truthy(hit):
            return "win"
        if _falsey(hit):
            return "loss"

    text = str(result or "").strip().lower()
    aliases = {
        "won": "win",
        "winner": "win",
        "hit": "win",
        "cash": "win",
        "true": "win",
        "1": "win",
        "lost": "loss",
        "loser": "loss",
        "miss": "loss",
        "false": "loss",
        "0": "loss",
        "tie": "push",
        "pushed": "push",
        "cancelled": "void",
        "canceled": "void",
        "no_action": "void",
        "na": "ungraded",
        "none": "ungraded",
        "missing": "ungraded",
    }
    normalized = aliases.get(text, text)
    return normalized if normalized in SUPPORTED_RESULTS else "ungraded"


def is_label_field(name: str) -> bool:
    return str(name or "").strip() in set(LABEL_FIELDS)


def label_field_names() -> list[str]:
    return list(LABEL_FIELDS)


def assert_label_not_in_features(feature_payload: Mapping[str, Any]) -> None:
    leaking = sorted(_find_label_only_fields(feature_payload))
    if leaking:
        raise ValueError(f"Label/postgame fields are not allowed in feature columns: {', '.join(leaking)}")


def _find_label_only_fields(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            text = str(key)
            if text in LABEL_ONLY_FIELDS:
                found.add(text)
            found.update(_find_label_only_fields(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_label_only_fields(item))
    return found


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "win", "hit"}


def _falsey(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    return str(value or "").strip().lower() in {"0", "false", "no", "n", "loss", "miss"}
