from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FEATURE_SCHEMA_VERSION = "ml-player-prop-features.sprint13c.v1"

SAFE_GAME_MARKET_FEATURES: tuple[str, ...] = (
    "game_market_available",
    "game_market_game_id",
    "game_market_consensus_open_total",
    "game_market_consensus_current_total",
    "game_market_total_line_movement",
    "game_market_favorite_team_open",
    "game_market_favorite_team_current",
    "game_market_team_is_favorite_open",
    "game_market_team_is_favorite_current",
    "game_market_team_no_vig_win_prob_open",
    "game_market_team_no_vig_win_prob_current",
    "game_market_opponent_no_vig_win_prob_open",
    "game_market_opponent_no_vig_win_prob_current",
    "game_market_book_count_moneyline",
    "game_market_book_count_total",
    "game_market_book_count_runline",
    "game_market_disagreement_score",
    "game_market_team_moneyline_movement",
    "game_market_opponent_moneyline_movement",
    "game_market_quality_flags",
    "game_market_enrichment_status",
)

SAFE_PROP_FEATURES: tuple[str, ...] = (
    "feature_schema_version",
    "exported_at",
    "source",
    "source_row_id",
    "prop_key",
    "date",
    "season",
    "player",
    "team",
    "opponent",
    "market",
    "side",
    "line",
    "book",
    "american_odds",
    "implied_probability_percent",
    "model_probability_percent",
    "hit_rate_summary",
)

SAFE_FEATURES: tuple[str, ...] = SAFE_PROP_FEATURES + SAFE_GAME_MARKET_FEATURES

BLOCKED_FEATURES: frozenset[str] = frozenset(
    {
        "home_score",
        "homeScore",
        "away_score",
        "awayScore",
        "total_runs",
        "totalRuns",
        "home_win",
        "homeWin",
        "away_win",
        "awayWin",
        "game_status",
        "gameStatus",
        "gameStatusText",
        "result",
        "hit",
        "push",
        "void",
        "push_flag",
        "pushFlag",
        "actual_value",
        "actualValue",
        "actualStat",
        "profit_1u",
        "profit1u",
        "profitUnits",
        "graded_at",
        "gradedAt",
        "grade",
        "riskBucket",
        "risk_bucket",
        "closing_line_value",
        "closingLineValue",
        "clv",
        "game_market_grade",
        "game_market_result",
        "game_market_profit_1u",
        "game_market_closing_line_value",
        "historical_game_market_grade",
        "historical_game_market_result",
        "historical_game_market_profit_1u",
        "historical_game_market_closing_line_value",
    }
)

_SAFE_FEATURE_SET = frozenset(SAFE_FEATURES)
_BLOCKED_LOWER = frozenset(name.lower() for name in BLOCKED_FEATURES)


def is_safe_feature_name(name: str) -> bool:
    """Return true only for explicit Sprint 13C ML export fields."""

    text = str(name or "").strip()
    return bool(text and text in _SAFE_FEATURE_SET and text.lower() not in _BLOCKED_LOWER)


def assert_no_leakage_fields(payload: Mapping[str, Any]) -> None:
    leaking = sorted(_find_blocked_names(payload))
    if leaking:
        raise ValueError(f"Blocked leakage fields are not allowed in ML features: {', '.join(leaking)}")


def filter_safe_features(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in payload.items() if is_safe_feature_name(str(key))}


def safe_game_market_feature_names() -> list[str]:
    return list(SAFE_GAME_MARKET_FEATURES)


def blocked_feature_names() -> set[str]:
    return set(BLOCKED_FEATURES)


def safe_feature_names() -> list[str]:
    return list(SAFE_FEATURES)


def leakage_fields_in_payload(payload: Mapping[str, Any]) -> set[str]:
    return _find_blocked_names(payload)


def _find_blocked_names(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            text = str(key)
            if text in BLOCKED_FEATURES or text.lower() in _BLOCKED_LOWER:
                found.add(text)
            found.update(_find_blocked_names(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_blocked_names(item))
    return found
