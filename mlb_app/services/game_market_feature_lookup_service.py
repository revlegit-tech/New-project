from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.warehouse_utils import clean, first
from mlb_app.services.team_match_utils import normalize_team_alias

MATCHED = "matched"
MISSING_DATE = "missing_date"
MISSING_TEAM = "missing_team"
MISSING_OPPONENT = "missing_opponent"
AMBIGUOUS_MATCH = "ambiguous_match"
WAREHOUSE_UNAVAILABLE = "warehouse_unavailable"
NOT_FOUND = "not_found"

GAME_MARKET_ENRICHED_FIELDS: tuple[str, ...] = (
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

LEAKAGE_FORBIDDEN_GAME_MARKET_KEYS = {
    "home_score",
    "away_score",
    "total_runs",
    "home_win",
    "away_win",
    "game_status",
    "gameStatusText",
    "result",
    "push_flag",
    "profit_1u",
    "closing_line_value",
    "graded_at",
}


class GameMarketFeatureLookupService:
    """Safe Sprint 13B enrichment interface for prop rows."""

    def __init__(
        self,
        repository: HistoricalGameOddsRepository | None,
        *,
        settings: Settings = default_settings,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.last_request_stats: dict[str, Any] = self._empty_stats()

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "game_market_enrichment_enabled", True))

    def feature_for_matchup(self, *, date: str, team: str, opponent: str) -> dict[str, Any]:
        """Return one safe feature dict for legacy single-context callers."""

        rows = [{"date": date, "team": team, "opponent": opponent}]
        enriched = self.enrich_rows(rows)
        return {key: enriched[0].get(key) for key in GAME_MARKET_ENRICHED_FIELDS if key in enriched[0]} if enriched else {}

    def enrich_rows(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Attach safe game-market fields with at most one feature query per date."""

        output = [dict(row) for row in rows]
        stats = self._empty_stats(row_count=len(output))
        contexts: list[tuple[int, str, str, str, str]] = []
        dates: set[str] = set()

        for index, row in enumerate(output):
            date_label = _date_from_row(row)
            team = normalize_team_alias(first(row, "team", "team_abbr", "teamAbbr", "teamCode"))
            opponent = normalize_team_alias(first(row, "opponent", "opponent_abbr", "opponentAbbr", "opponentCode"))
            missing_status = _missing_status(date_label=date_label, team=team, opponent=opponent)
            if missing_status:
                output[index].update(_no_match(missing_status))
                stats["status_counts"][missing_status] += 1
                continue
            contexts.append((index, date_label, team, opponent, _matchup_key(date_label, team, opponent)))
            dates.add(date_label)

        if not contexts:
            self._finish_stats(stats, output)
            return output

        if not self.enabled or self.repository is None:
            for index, *_rest in contexts:
                output[index].update(_no_match(WAREHOUSE_UNAVAILABLE))
                stats["status_counts"][WAREHOUSE_UNAVAILABLE] += 1
            self._finish_stats(stats, output, source="disabled" if not self.enabled else "unavailable")
            return output

        features_by_date: dict[str, list[dict[str, Any]]] = {}
        failed_dates: set[str] = set()
        for date_label in sorted(dates):
            try:
                features_by_date[date_label] = [dict(row) for row in self.repository.query_features_by_date(date_label)]
                stats["date_query_count"] += 1
                stats["feature_rows_loaded"] += len(features_by_date[date_label])
            except Exception as error:
                failed_dates.add(date_label)
                stats["warnings"].append(f"Game-market features unavailable for {date_label}: {type(error).__name__}: {error}")

        lookup_cache: dict[str, dict[str, Any]] = {}
        for index, date_label, team, opponent, cache_key in contexts:
            if date_label in failed_dates:
                feature = _no_match(WAREHOUSE_UNAVAILABLE)
            elif cache_key in lookup_cache:
                feature = dict(lookup_cache[cache_key])
            else:
                feature = self._feature_from_date_rows(features_by_date.get(date_label, []), team=team, opponent=opponent)
                lookup_cache[cache_key] = dict(feature)
            output[index].update(feature)
            stats["status_counts"][clean(feature.get("game_market_enrichment_status")) or NOT_FOUND] += 1

        self._finish_stats(stats, output)
        return output

    def status_payload(self) -> dict[str, Any]:
        stats = dict(self.last_request_stats)
        stats["status_counts"] = dict(stats.get("status_counts") or {})
        return {
            "enabled": self.enabled,
            "source": "historical_game_market_features",
            "matched_rows_last_request": int(stats.get("matched_rows") or 0),
            "rows_last_request": int(stats.get("row_count") or 0),
            "status_counts_last_request": stats["status_counts"],
            "date_query_count_last_request": int(stats.get("date_query_count") or 0),
            "feature_rows_loaded_last_request": int(stats.get("feature_rows_loaded") or 0),
            "warnings": list(stats.get("warnings") or []),
        }

    def _feature_from_date_rows(self, features: Sequence[Mapping[str, Any]], *, team: str, opponent: str) -> dict[str, Any]:
        candidates = [
            dict(row)
            for row in features
            if _teams_match(row, team=team, opponent=opponent)
        ]
        if not candidates:
            return _no_match(NOT_FOUND)
        if len(candidates) > 1:
            return _no_match(AMBIGUOUS_MATCH)
        return _safe_feature_dict(candidates[0], team=team, opponent=opponent)

    @staticmethod
    def _empty_stats(*, row_count: int = 0) -> dict[str, Any]:
        return {
            "row_count": row_count,
            "matched_rows": 0,
            "available_rows": 0,
            "date_query_count": 0,
            "feature_rows_loaded": 0,
            "status_counts": Counter(),
            "source": "historical_game_market_features",
            "warnings": [],
        }

    def _finish_stats(self, stats: dict[str, Any], rows: Sequence[Mapping[str, Any]], *, source: str = "historical_game_market_features") -> None:
        stats["source"] = source
        stats["matched_rows"] = sum(1 for row in rows if row.get("game_market_enrichment_status") == MATCHED)
        stats["available_rows"] = sum(1 for row in rows if bool(row.get("game_market_available")))
        stats["status_counts"] = dict(stats.get("status_counts") or {})
        stats["warnings"] = list(stats.get("warnings") or [])[:10]
        self.last_request_stats = dict(stats)


def _safe_feature_dict(row: Mapping[str, Any], *, team: str, opponent: str) -> dict[str, Any]:
    leaking = LEAKAGE_FORBIDDEN_GAME_MARKET_KEYS.intersection(row.keys())
    if leaking:
        return _no_match(WAREHOUSE_UNAVAILABLE)

    away_team = normalize_team_alias(row.get("away_team"))
    home_team = normalize_team_alias(row.get("home_team"))
    if team == home_team:
        team_side = "home"
        opponent_side = "away"
    elif team == away_team:
        team_side = "away"
        opponent_side = "home"
    else:
        return _no_match(NOT_FOUND)

    favorite_open = normalize_team_alias(row.get("favorite_team_open"))
    favorite_current = normalize_team_alias(row.get("favorite_team_current"))
    quality_flags = row.get("quality_flags")
    if not isinstance(quality_flags, list):
        quality_flags = [clean(quality_flags)] if clean(quality_flags) else []

    return {
        "game_market_available": True,
        "game_market_game_id": clean(row.get("game_id")),
        "game_market_consensus_open_total": row.get("consensus_open_total"),
        "game_market_consensus_current_total": row.get("consensus_current_total"),
        "game_market_total_line_movement": row.get("total_line_movement"),
        "game_market_favorite_team_open": favorite_open,
        "game_market_favorite_team_current": favorite_current,
        "game_market_team_is_favorite_open": favorite_open == team if favorite_open else False,
        "game_market_team_is_favorite_current": favorite_current == team if favorite_current else False,
        "game_market_team_no_vig_win_prob_open": row.get(f"{team_side}_no_vig_win_prob_open"),
        "game_market_team_no_vig_win_prob_current": row.get(f"{team_side}_no_vig_win_prob_current"),
        "game_market_opponent_no_vig_win_prob_open": row.get(f"{opponent_side}_no_vig_win_prob_open"),
        "game_market_opponent_no_vig_win_prob_current": row.get(f"{opponent_side}_no_vig_win_prob_current"),
        "game_market_book_count_moneyline": row.get("book_count_moneyline"),
        "game_market_book_count_total": row.get("book_count_total"),
        "game_market_book_count_runline": row.get("book_count_runline"),
        "game_market_disagreement_score": row.get("market_disagreement_score"),
        "game_market_team_moneyline_movement": _movement(
            row.get(f"{team_side}_open_moneyline_consensus"),
            row.get(f"{team_side}_current_moneyline_consensus"),
        ),
        "game_market_opponent_moneyline_movement": _movement(
            row.get(f"{opponent_side}_open_moneyline_consensus"),
            row.get(f"{opponent_side}_current_moneyline_consensus"),
        ),
        "game_market_quality_flags": [clean(item) for item in quality_flags if clean(item)],
        "game_market_enrichment_status": MATCHED,
    }


def _teams_match(row: Mapping[str, Any], *, team: str, opponent: str) -> bool:
    away_team = normalize_team_alias(row.get("away_team"))
    home_team = normalize_team_alias(row.get("home_team"))
    return (
        bool(team and opponent and away_team and home_team)
        and ((away_team == team and home_team == opponent) or (away_team == opponent and home_team == team))
    )


def _no_match(status: str) -> dict[str, Any]:
    return {
        "game_market_available": False,
        "game_market_enrichment_status": status,
    }


def _missing_status(*, date_label: str, team: str, opponent: str) -> str:
    if not date_label:
        return MISSING_DATE
    if not team:
        return MISSING_TEAM
    if not opponent:
        return MISSING_OPPONENT
    return ""


def _date_from_row(row: Mapping[str, Any]) -> str:
    return clean(first(row, "date", "game_date", "gameDate", "slateDate"))


def _matchup_key(date_label: str, team: str, opponent: str) -> str:
    return "|".join((date_label, team, opponent))


def _movement(open_value: Any, current_value: Any) -> float | None:
    open_number = _float_or_none(open_value)
    current_number = _float_or_none(current_value)
    if open_number is None or current_number is None:
        return None
    return round(current_number - open_number, 4)


def _float_or_none(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None
