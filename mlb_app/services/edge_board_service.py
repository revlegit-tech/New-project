from __future__ import annotations
import re
import time

import csv
from pathlib import Path
from typing import Any, Hashable

from mlb_app.config import settings as default_settings
from mlb_app.observability.metrics import MetricsRegistry
from mlb_app.services.board_cache import BoardCache, BoardCacheBuildResult
from mlb_app.services.model_card_service import ModelCardService
from mlb_app.services.playerboard_read_service import prop_key_for_row
from mlb_app.services.playerboard_service import PlayerboardService

EDGE_BOARD_VERSION = "2026-05-edge-board-v1"


class EdgeBoardService:
    """Bettor-facing board adapter for ranked playerboard rows.

    The legacy playerboard endpoint remains available for compatibility. This
    service reshapes those rows into a product contract that is safe to render
    on the Today page: conservative decision labels, market readiness, grading
    context, and concise risk/reason copy.
    """

    def __init__(
        self,
        *,
        playerboard_service: PlayerboardService | None = None,
        model_card_service: ModelCardService | None = None,
        board_cache: BoardCache | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.playerboard_service = playerboard_service or PlayerboardService()
        self.model_card_service = model_card_service or ModelCardService()
        self.metrics = metrics
        self.board_cache = board_cache or BoardCache(
            ttl_seconds=default_settings.board_cache_ttl_seconds,
            max_keys=default_settings.board_cache_max_keys,
            metrics=metrics,
        )
        self._cards: dict[str, dict[str, Any]] = {}

    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        cache_key = _board_cache_key(query)
        dependency_paths = _playerboard_dependency_paths(query)

        # Explicit refresh/save requests are operator-intent paths. Do not serve
        # them from cache, but store the fresh result for subsequent normal reads.
        if _bypass_board_cache(query):
            payload = self._timed_build_payload(query)
            result = self.board_cache.set(cache_key, payload, dependency_paths=dependency_paths)
            return self._with_board_cache_metadata(result, served_from_cache=False, reason="bypass_refresh_or_save")

        result = self.board_cache.get_or_build(
            cache_key,
            lambda: self._timed_build_payload(query),
            dependency_paths=dependency_paths,
        )
        return self._with_board_cache_metadata(result, served_from_cache=result.hit, reason=result.reason)

    def _timed_build_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        started_at = time.perf_counter()
        payload = self._build_payload(query)
        if self.metrics is not None:
            self.metrics.observe("board_build_duration_ms", round((time.perf_counter() - started_at) * 1000.0, 3), labels={"layer": "edge_board"})
        return payload

    def _build_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        board = self.playerboard_service.board_payload(query)
        raw_rows = _list_rows(board.get("top") or board.get("rows") or [])
        game_context_index = _phase18_v7_game_context_index(query, board)
        self._cards = self._load_cards()
        rows = [
            self._enrich_row(_phase18_v7_merge_game_context(row, game_context_index), index + 1, board)
            for index, row in enumerate(raw_rows)
        ]

        return {
            "status": "ok",
            "schemaVersion": board.get("schemaVersion"),
            "version": EDGE_BOARD_VERSION,
            "season": board.get("season"),
            "date": board.get("date") or board.get("latestAvailableDate"),
            "cacheHit": bool(board.get("cacheHit")),
            "rows": rows,
            "rowCount": len(rows),
            "source": {
                "cardsBuilt": board.get("cardsBuilt", 0),
                "propsLoaded": board.get("propsLoaded", 0),
                "message": board.get("message", ""),
                "saved": board.get("saved", {}),
                "gameContextJoin": {
                    "source": "data/warehouse/game_context/game_context_DATE.csv",
                    "contextRows": len(game_context_index),
                    "matchedRows": sum(1 for row in rows if _clean(row.get("game_context_source"))),
                    "date": _phase18_v7_context_date(query, board),
                },
            },
            "filters": self._filter_options(rows),
            "summary": self._summary(rows),
            "trust": board.get("trust", {}),
            "productState": board.get("productState"),
            "latestFullyGradedDate": board.get("latestFullyGradedDate", ""),
            "dataConfidence": board.get("dataConfidence", "Missing"),
            "modelReadiness": board.get("modelReadiness", {}),
            "freshness": board.get("freshness", {}),
            "meta": {
                "snapshotSignature": ((board.get("sourceMeta") or {}).get("snapshotSignature")),
                "source": board.get("source"),
            },
        }

    def row_for_detail(self, query: dict[str, list[str]]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return one enriched row for prop detail without building the full board."""

        if not hasattr(self.playerboard_service, "snapshot_for_query"):
            return {}, {"lookupMode": "unavailable"}
        snapshot = self.playerboard_service.snapshot_for_query(query)
        prop_key = _query_value(query, "propKey") or _query_value(query, "id")
        row: dict[str, Any] = {}
        lookup_mode = "prop_key"
        if prop_key:
            row = snapshot.row_for_prop_key(prop_key)
        if not row:
            lookup_mode = "fallback_match"
            row = _find_snapshot_row(list(snapshot.rows), query)
        if not row:
            health = snapshot.health.to_dict()
            return {}, {
                "lookupMode": lookup_mode,
                "snapshot": snapshot.source_meta(),
                "freshness": health.get("freshness", {}),
            }
        health = snapshot.health.to_dict()
        self._cards = self._load_cards()
        enriched = self._enrich_row(row, 1, {
            "productState": dict(snapshot.product_state),
            "dataConfidence": health.get("dataConfidence", "Missing"),
            "latestFullyGradedDate": health.get("latestFullyGradedDate", ""),
        })
        return enriched, {
            "lookupMode": lookup_mode,
            "snapshot": snapshot.source_meta(),
            "freshness": health.get("freshness", {}),
        }

    def _with_board_cache_metadata(
        self,
        result: BoardCacheBuildResult,
        *,
        served_from_cache: bool,
        reason: str,
    ) -> dict[str, Any]:
        payload = dict(result.payload)
        source = dict(payload.get("source") or {})
        source["boardCache"] = {
            "hit": served_from_cache,
            "reason": reason,
            "key": repr(result.key),
            "ageSeconds": round(result.age_seconds, 3),
            "ttlRemainingSeconds": round(result.ttl_remaining_seconds, 3),
            "dependencyCount": len(result.signatures),
        }
        payload["source"] = source
        payload["boardCache"] = source["boardCache"]
        # Preserve the existing top-level cacheHit boolean while making the new
        # architecture-boundary cache visible to the UI and logs.
        payload["cacheHit"] = bool(payload.get("cacheHit")) or served_from_cache
        return payload

    def _load_cards(self) -> dict[str, dict[str, Any]]:
        payload = self.model_card_service.payload({})
        cards: dict[str, dict[str, Any]] = {}
        for card in payload.get("markets") or []:
            market = _clean(card.get("market")).lower()
            if market:
                cards[market] = card
        return cards

    def _card_for(self, market: str) -> dict[str, Any]:
        key = _clean(market).lower()
        if key in self._cards:
            return self._cards[key]
        # Fallback allows newly discovered playerboard markets to stay visible,
        # but they remain research-only if model governance cannot prove readiness.
        return self.model_card_service.card_for_market(key) if key else {}

    def _enrich_row(self, row: dict[str, Any], rank: int, board: dict[str, Any]) -> dict[str, Any]:
        market = _clean(row.get("market"))
        card = self._card_for(market)
        edge = _float(_first(row, "finalEdgePercent", "edgePercent", "edge", "modelEdgePercent"))
        probability = _float(_first(row, "finalProbabilityPercent", "probabilityPercent", "modelProbabilityPercent", "probability"))
        implied = _float(_first(row, "impliedProbabilityPercent", "bookImpliedProbabilityPercent", "impliedPercent"))
        confidence = _clean(_first(row, "confidence", "confidenceLabel")) or "Research"
        decision_label = _decision_label(card, edge, confidence, _clean(row.get("recommendation")))
        readiness = _clean(card.get("readinessLabel") or card.get("productionStatus") or "Research only")
        latest_graded = _clean(card.get("latestGradedDate") or board.get("latestFullyGradedDate"))
        warnings = list(card.get("trustWarnings") or [])
        book = _clean(_first(row, "book", "sportsbook", "bestBook", "bookmaker", "sourceBook"))
        freshness = _row_freshness(row, board)

        enriched = dict(row)
        game_context = _game_context_for_row(row)
        enriched.update(
            {
                "id": _row_id(row, rank),
                "propKey": prop_key_for_row(row),
                "rank": rank,
                "player": _clean(_first(row, "player", "playerName", "name")),
                "team": _clean(row.get("team")),
                "opponent": _clean(row.get("opponent")),
                "market": market,
                "marketDisplay": _clean(row.get("marketDisplay")) or _title(market),
                "line": _clean(row.get("line")),
                "americanOdds": _clean(_first(row, "americanOdds", "odds", "price")),
                "book": book or "Best available",
                "gameTime": _clean(_first(row, "gameTime", "startTime", "commenceTime", "game_time")),
                "decisionLabel": decision_label,
                "decisionTone": _decision_tone(decision_label),
                "modelProbabilityPercent": _round_or_blank(probability),
                "impliedProbabilityPercent": _round_or_blank(implied),
                "edgePercent": _round_or_blank(edge),
                "confidence": confidence,
                "readinessLabel": readiness,
                "productionStatus": _clean(card.get("productionStatus") or "research_only"),
                "canShowConfidentPick": bool(card.get("canShowConfidentPick")),
                "trainingRows": int(card.get("trainingRows") or 0),
                "positiveRows": int(card.get("positiveRows") or 0),
                "negativeRows": int(card.get("negativeRows") or 0),
                "latestGradedDate": latest_graded,
                "calibrationStatus": _clean((card.get("calibration") or {}).get("status")) or "uncalibrated",
                "warningCount": len(warnings),
                "trustWarnings": warnings[:6],
                "reasons": _reasons(row, card, edge, probability, implied, latest_graded),
                "suggestedStake": _suggested_stake(decision_label, bool(card.get("canShowConfidentPick"))),
                "modelCard": {
                    "market": card.get("market") or market,
                    "readinessLabel": readiness,
                    "productionStatus": card.get("productionStatus") or "research_only",
                    "canShowConfidentPick": bool(card.get("canShowConfidentPick")),
                },
                "trust": _row_trust(
                    row=row,
                    market=market,
                    readiness=readiness,
                    card=card,
                    edge=edge,
                    probability=probability,
                    implied=implied,
                    decision_label=decision_label,
                    warnings=warnings,
                    book=book or "Best available",
                ),
                "freshness": freshness,
            }
        )
        # PHASE18_V4_CONTEXT_JOIN_START
        if game_context:
            enriched.update(game_context)
        # PHASE18_V4_CONTEXT_JOIN_END
        return enriched

    @staticmethod
    def _filter_options(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
        return {
            "markets": _unique(row.get("market") for row in rows),
            "teams": _unique(row.get("team") for row in rows),
            "books": _unique(row.get("book") for row in rows),
            "readiness": _unique(row.get("readinessLabel") for row in rows),
            "confidence": _unique(row.get("confidence") for row in rows),
            "decisions": _unique(row.get("decisionLabel") for row in rows),
        }

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        decisions: dict[str, int] = {}
        readiness: dict[str, int] = {}
        for row in rows:
            decisions[_clean(row.get("decisionLabel")) or "Unknown"] = decisions.get(_clean(row.get("decisionLabel")) or "Unknown", 0) + 1
            readiness[_clean(row.get("readinessLabel")) or "Unknown"] = readiness.get(_clean(row.get("readinessLabel")) or "Unknown", 0) + 1
        return {
            "rows": len(rows),
            "decisionCounts": decisions,
            "readinessCounts": readiness,
            "confidentRows": sum(1 for row in rows if row.get("canShowConfidentPick")),
            "warningRows": sum(1 for row in rows if int(row.get("warningCount") or 0) > 0),
        }



GAME_CONTEXT_FIELDS = (
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
    "park_factor",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_wind_direction",
    "weather_humidity",
    "weather_precip_probability",
    "roof_status",
    "venue",
    "game_context_source",
)

GAME_CONTEXT_ALIASES = {
    "team_moneyline": "teamMoneyline",
    "opponent_moneyline": "opponentMoneyline",
    "game_total": "gameTotal",
    "moneyline_implied_probability": "moneylineImpliedProbability",
    "team_implied_runs": "teamImpliedRuns",
    "opponent_implied_runs": "opponentImpliedRuns",
    "opponent_implied_runs_proxy": "opponentImpliedRunsProxy",
    "park_factor": "parkFactor",
    "weather_temperature_f": "weatherTemperatureF",
    "weather_wind_mph": "weatherWindMph",
    "weather_wind_direction": "weatherWindDirection",
    "weather_humidity": "weatherHumidity",
    "weather_precip_probability": "weatherPrecipProbability",
    "roof_status": "roofStatus",
    "game_context_source": "gameContextSource",
}


def _load_game_context_for_board(board: dict[str, Any], query: dict[str, list[str]]) -> dict[tuple[str, str], dict[str, str]]:
    """Load canonical Phase 17 game context rows for API row enrichment.

    Playerboard remains the hot path, but the source of truth for game lines,
    implied runs, weather, venue, and park context is the separate game-context
    layer. This bridge joins those fields back onto EdgeBoard rows so the UI
    does not show stale `Missing` values after the context layer is populated.
    """

    date_label = _clean(board.get("date") or board.get("latestAvailableDate") or _query_value(query, "date"))
    if not date_label:
        return {}
    path = Path("data") / "warehouse" / "game_context" / f"game_context_{date_label}.csv"
    if not path.exists():
        return {}

    contexts: dict[tuple[str, str], dict[str, str]] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if not isinstance(row, dict):
                    continue
                team = _context_team(row, "team")
                opponent = _context_team(row, "opponent")
                if not team or not opponent:
                    continue
                contexts[(team, opponent)] = row
    except OSError:
        return {}
    return contexts


def _merge_game_context(row: dict[str, Any], contexts: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    if not contexts:
        return row
    key = (_context_team(row, "team"), _context_team(row, "opponent"))
    context = contexts.get(key)
    if not context:
        return row

    merged = dict(row)
    for field in GAME_CONTEXT_FIELDS:
        value = context.get(field)
        if value not in {None, ""} and merged.get(field) in {None, ""}:
            merged[field] = value
        alias = GAME_CONTEXT_ALIASES.get(field)
        if alias and value not in {None, ""} and merged.get(alias) in {None, ""}:
            merged[alias] = value
    return merged


def _context_team(row: dict[str, Any], key: str) -> str:
    aliases = {
        "team": ("team", "team_abbr", "teamAbbr", "team_code", "teamCode"),
        "opponent": ("opponent", "opponent_abbr", "opponentAbbr", "opponent_code", "opponentCode"),
    }
    for alias in aliases.get(key, (key,)):
        value = _clean(row.get(alias)).upper()
        if value:
            return value
    return ""


def _board_cache_key(query: dict[str, list[str]]) -> Hashable:
    season = _int_query(query, "season", default_settings.current_season)
    date_label = _query_value(query, "date")
    market = _query_value(query, "market").lower()
    limit = _int_query(query, "limit", 50)
    return (EDGE_BOARD_VERSION, season, date_label, market, limit)


def _playerboard_dependency_paths(query: dict[str, list[str]]) -> tuple[Path, ...]:
    season = _int_query(query, "season", default_settings.current_season)
    return (default_settings.data_dir / "playerboard" / f"playerboard_{season}.csv",)


def _bypass_board_cache(query: dict[str, list[str]]) -> bool:
    return _truthy_query(query, "refresh") or _truthy_query(query, "save")


def _query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key) or [default]
    return _clean(values[0] if values else default)


def _int_query(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(_query_value(query, key, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _truthy_query(query: dict[str, list[str]], key: str) -> bool:
    return _query_value(query, key).lower() in {"1", "true", "yes", "on"}


def _list_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_blank(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _title(value: str) -> str:
    return _clean(value).replace("_", " ").title() or "Market"


def _row_id(row: dict[str, Any], rank: int) -> str:
    parts = [row.get("date"), row.get("player"), row.get("team"), row.get("market"), row.get("line"), row.get("americanOdds")]
    text = "|".join(_clean(part).lower() for part in parts if _clean(part))
    return text or f"edge-row-{rank}"


def _decision_label(card: dict[str, Any], edge: float | None, confidence: str, recommendation: str) -> str:
    rec = recommendation.lower()
    if "avoid" in rec or "negative" in rec or (edge is not None and edge <= 0):
        return "No bet"
    if card.get("canShowConfidentPick") and edge is not None and edge >= 2:
        return "Potential edge"
    status = _clean(card.get("productionStatus")).lower()
    if status in {"experimental", "production_candidate", "production"} and edge is not None and edge > 0:
        return "Model lean"
    if edge is not None and edge > 0:
        return "Watchlist"
    if confidence.lower() in {"high", "medium"}:
        return "Watchlist"
    return "No bet"


def _decision_tone(label: str) -> str:
    key = label.lower().replace(" ", "-")
    if key == "potential-edge":
        return "positive"
    if key in {"model-lean", "watchlist"}:
        return "watch"
    return "muted"


def _suggested_stake(label: str, confident: bool) -> str:
    if label == "Potential edge" and confident:
        return "0.25u capped"
    if label in {"Watchlist", "Model lean"}:
        return "Research only"
    return "0u"


def _row_trust(
    *,
    row: dict[str, Any],
    market: str,
    readiness: str,
    card: dict[str, Any],
    edge: float | None,
    probability: float | None,
    implied: float | None,
    decision_label: str,
    warnings: list[Any],
    book: str,
) -> dict[str, Any]:
    confident = bool(card.get("canShowConfidentPick"))
    production_status = _clean(card.get("productionStatus") or "research_only")
    action_status = _actionability_status(decision_label, confident, edge)
    return {
        "propIdentity": {
            "player": _clean(_first(row, "player", "playerName", "name")),
            "team": _clean(row.get("team")),
            "opponent": _clean(row.get("opponent")),
            "market": market,
            "line": _clean(row.get("line")),
            "side": _clean(_first(row, "side", "rawLabel", "pickSide")) or "Over",
            "book": book,
        },
        "modelEdge": {
            "edgePercent": _round_float(edge),
            "modelProbabilityPercent": _round_float(probability),
            "impliedProbabilityPercent": _round_float(implied),
            "tone": "positive" if edge and edge > 0 else "negative" if edge and edge < 0 else "neutral",
        },
        "readiness": {
            "label": readiness,
            "status": production_status,
            "tone": _readiness_tone(readiness, production_status, confident),
            "canShowConfidentPick": confident,
            "warnings": [_clean(item) for item in warnings[:6] if _clean(item)],
        },
        "actionability": {
            "label": _actionability_label(action_status, decision_label),
            "status": action_status,
            "suggestedStake": _suggested_stake(decision_label, confident),
            "stakeUnits": 0.25 if action_status == "actionable" else 0,
            "reason": _actionability_reason(action_status),
        },
    }


def _row_freshness(row: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    freshness = board.get("freshness") if isinstance(board.get("freshness"), dict) else {}
    status = _freshness_status(freshness, board)
    return {
        "label": _freshness_label(status),
        "status": status,
        "tone": "good" if status == "fresh" else "risk" if status in {"stale", "missing"} else "watch",
        "ageSeconds": freshness.get("ageSeconds"),
        "source": _clean(freshness.get("snapshotBuiltAt") or freshness.get("source") or board.get("date") or row.get("date")),
    }


def _round_float(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _readiness_tone(label: str, status: str, confident: bool) -> str:
    raw = f"{label} {status}".lower()
    if confident or "production ready" in raw or "production_ready" in raw:
        return "good"
    if "missing" in raw or "no model" in raw or "blocked" in raw or "stale" in raw:
        return "risk"
    return "watch"


def _actionability_status(label: str, confident: bool, edge: float | None) -> str:
    raw = label.lower()
    if "no bet" in raw or (edge is not None and edge <= 0):
        return "blocked"
    if confident and ("potential edge" in raw or (edge is not None and edge >= 2)):
        return "actionable"
    if raw in {"watchlist", "model lean"} or (edge is not None and edge > 0):
        return "watchlist"
    return "research_only"


def _actionability_label(status: str, decision_label: str) -> str:
    if status in {"actionable", "watchlist", "blocked"} and decision_label:
        return decision_label
    if status == "actionable":
        return "Actionable"
    if status == "watchlist":
        return "Watchlist"
    if status == "blocked":
        return "No bet"
    return "Research only"


def _actionability_reason(status: str) -> str:
    if status == "actionable":
        return "Model edge and readiness gates clear the conservative action threshold."
    if status == "watchlist":
        return "Positive edge is visible, but readiness or stake policy keeps this research-first."
    if status == "blocked":
        return "The row does not clear the model edge threshold."
    return "Research-only until data and model gates are satisfied."


def _freshness_status(freshness: dict[str, Any], board: dict[str, Any]) -> str:
    raw = _clean(freshness.get("status") or board.get("dataConfidence")).lower()
    age = freshness.get("ageSeconds")
    if raw in {"missing", "failed", "unavailable"}:
        return "missing"
    if isinstance(age, (int, float)):
        if age > 900:
            return "stale"
        if age > 300:
            return "aging"
    if raw in {"stale", "red"}:
        return "stale"
    if raw in {"fresh", "good", "ok"}:
        return "fresh"
    if raw in {"partial", "degraded", "aging", "warning", "warn"}:
        return "aging"
    return "unknown"


def _freshness_label(status: str) -> str:
    return {
        "fresh": "Fresh",
        "aging": "Aging",
        "stale": "Stale",
        "missing": "Missing",
    }.get(status, "Unknown")


def _reasons(
    row: dict[str, Any],
    card: dict[str, Any],
    edge: float | None,
    probability: float | None,
    implied: float | None,
    latest_graded: str,
) -> list[str]:
    reasons: list[str] = []
    if edge is not None:
        if edge > 0:
            reasons.append(f"Model price is {edge:.2f} percentage points above the book-implied price.")
        else:
            reasons.append("Book price does not clear the model edge threshold.")
    elif probability is not None and implied is not None:
        reasons.append("Model and book probabilities are available for review.")
    else:
        reasons.append("Model edge inputs are incomplete; keep this row research-only.")

    rows = int(card.get("trainingRows") or 0)
    if rows:
        reasons.append(f"Market model card reports {rows:,} training rows.")
    else:
        reasons.append("No market-specific training sample is available yet.")

    if latest_graded:
        reasons.append(f"Latest fully graded slate: {latest_graded}.")
    else:
        reasons.append("No fully graded slate is available for promotion gates.")

    return reasons[:3]


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return sorted(result)

# PHASE18_V4_CONTEXT_HELPERS_START
_GAME_CONTEXT_CACHE: dict[tuple[str, tuple[int, int]], dict[tuple[str, str], dict[str, str]]] = {}
_GAME_CONTEXT_FIELDS = (
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
    "park_factor",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_wind_direction",
    "weather_humidity",
    "weather_precip_probability",
    "roof_status",
    "venue",
    "game_context_source",
)
_TEAM_ALIASES = {"SD": "SDP", "SF": "SFG", "CWS": "CHW", "WSH": "WSN", "TB": "TBR", "KC": "KCR", "OAK": "ATH"}


def _context_team(value: Any) -> str:
    text = _clean(value).upper()
    return _TEAM_ALIASES.get(text, text)


def _context_file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _game_context_path(date_label: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "warehouse" / "game_context" / f"game_context_{date_label}.csv"


def _load_game_context(date_label: str) -> dict[tuple[str, str], dict[str, str]]:
    if not date_label:
        return {}
    path = _game_context_path(date_label)
    signature = _context_file_signature(path)
    if signature is None:
        return {}
    cache_key = (date_label, signature)
    cached = _GAME_CONTEXT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    mapping: dict[tuple[str, str], dict[str, str]] = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                team = _context_team(row.get("team"))
                opponent = _context_team(row.get("opponent"))
                if team and opponent:
                    mapping[(team, opponent)] = row
    except Exception:
        return {}
    # Drop stale entries for this date and store the current mtime-aware mapping.
    for key in [key for key in _GAME_CONTEXT_CACHE if key[0] == date_label]:
        _GAME_CONTEXT_CACHE.pop(key, None)
    _GAME_CONTEXT_CACHE[cache_key] = mapping
    return mapping


def _game_context_for_row(row: dict[str, Any]) -> dict[str, str]:
    date_label = _clean(row.get("date"))
    team = _context_team(row.get("team"))
    opponent = _context_team(row.get("opponent"))
    if not date_label or not team or not opponent:
        return {}
    context = _load_game_context(date_label).get((team, opponent)) or {}
    if not context:
        return {}
    return {field: _clean(context.get(field)) for field in _GAME_CONTEXT_FIELDS if _clean(context.get(field))}
# PHASE18_V4_CONTEXT_HELPERS_END

# Phase 18 v5 compatibility shim: keep game-context joins tolerant of both
# legacy helper calls (_context_team(value)) and row/key calls
# (_context_team(row, "team")). This is intentionally appended so it overrides
# any earlier malformed helper without disturbing the rest of EdgeBoardService.
def _context_team(row, key: str = "") -> str:
    if isinstance(row, dict):
        value = ""
        if key:
            value = row.get(key) or row.get(key.lower()) or row.get(key.upper()) or ""
        if not value:
            value = row.get("team") or row.get("opponent") or row.get("home_team") or row.get("away_team") or ""
    else:
        value = row

    try:
        text = _clean(value).upper()
    except NameError:
        text = str(value or "").strip().upper()

    aliases = {
        "SD": "SDP",
        "SDP": "SDP",
        "SF": "SFG",
        "SFG": "SFG",
        "CWS": "CHW",
        "CHW": "CHW",
        "WSH": "WSN",
        "WSN": "WSN",
        "TB": "TBR",
        "TBR": "TBR",
        "KC": "KCR",
        "KCR": "KCR",
        "OAK": "ATH",
        "ATH": "ATH",
    }
    return aliases.get(text, text)

# Phase 18 v7: canonical game-context join helpers
_PHASE18_V7_CONTEXT_FIELDS = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
    "park_factor",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_wind_direction",
    "weather_humidity",
    "weather_precip_probability",
    "roof_status",
    "venue",
    "game_context_source",
    "moneyline_source",
    "total_source",
    "weather_source",
    "park_factor_source",
]

_PHASE18_V7_CAMEL_ALIASES = {
    "team_moneyline": "teamMoneyline",
    "opponent_moneyline": "opponentMoneyline",
    "game_total": "gameTotal",
    "moneyline_implied_probability": "moneylineImpliedProbability",
    "team_implied_runs": "teamImpliedRuns",
    "opponent_implied_runs": "opponentImpliedRuns",
    "park_factor": "parkFactor",
    "weather_temperature_f": "weatherTemperatureF",
    "weather_wind_mph": "weatherWindMph",
    "weather_wind_direction": "weatherWindDirection",
    "weather_humidity": "weatherHumidity",
    "weather_precip_probability": "weatherPrecipProbability",
    "roof_status": "roofStatus",
    "venue": "venue",
}

_PHASE18_V7_TEAM_ALIASES = {
    "ari": "ARI", "arizona": "ARI", "arizona diamondbacks": "ARI",
    "atl": "ATL", "atlanta": "ATL", "atlanta braves": "ATL",
    "bal": "BAL", "baltimore": "BAL", "baltimore orioles": "BAL",
    "bos": "BOS", "boston": "BOS", "boston red sox": "BOS",
    "chc": "CHC", "chicago cubs": "CHC", "cubs": "CHC",
    "chw": "CHW", "cws": "CHW", "chicago white sox": "CHW", "white sox": "CHW",
    "cin": "CIN", "cincinnati": "CIN", "cincinnati reds": "CIN",
    "cle": "CLE", "cleveland": "CLE", "cleveland guardians": "CLE",
    "col": "COL", "colorado": "COL", "colorado rockies": "COL",
    "det": "DET", "detroit": "DET", "detroit tigers": "DET",
    "hou": "HOU", "houston": "HOU", "houston astros": "HOU",
    "kc": "KCR", "kcr": "KCR", "kansas city": "KCR", "kansas city royals": "KCR",
    "laa": "LAA", "los angeles angels": "LAA", "angels": "LAA",
    "lad": "LAD", "los angeles dodgers": "LAD", "dodgers": "LAD",
    "mia": "MIA", "miami": "MIA", "miami marlins": "MIA",
    "mil": "MIL", "milwaukee": "MIL", "milwaukee brewers": "MIL",
    "min": "MIN", "minnesota": "MIN", "minnesota twins": "MIN",
    "nym": "NYM", "new york mets": "NYM", "mets": "NYM",
    "nyy": "NYY", "new york yankees": "NYY", "yankees": "NYY",
    "ath": "ATH", "oak": "ATH", "oakland athletics": "ATH", "athletics": "ATH", "a s": "ATH",
    "phi": "PHI", "philadelphia": "PHI", "philadelphia phillies": "PHI",
    "pit": "PIT", "pittsburgh": "PIT", "pittsburgh pirates": "PIT",
    "sd": "SDP", "sdp": "SDP", "san diego": "SDP", "san diego padres": "SDP", "padres": "SDP",
    "sea": "SEA", "seattle": "SEA", "seattle mariners": "SEA",
    "sf": "SFG", "sfg": "SFG", "san francisco": "SFG", "san francisco giants": "SFG",
    "stl": "STL", "st louis": "STL", "st louis cardinals": "STL", "saint louis cardinals": "STL", "cardinals": "STL",
    "tb": "TBR", "tbr": "TBR", "tampa bay": "TBR", "tampa bay rays": "TBR",
    "tex": "TEX", "texas": "TEX", "texas rangers": "TEX",
    "tor": "TOR", "toronto": "TOR", "toronto blue jays": "TOR",
    "wsh": "WSN", "wsn": "WSN", "washington": "WSN", "washington nationals": "WSN",
}


def _phase18_v7_context_date(query: dict[str, list[str]], board: dict[str, Any]) -> str:
    date_label = _query_value(query, "date")
    if date_label:
        return date_label
    return _clean(board.get("date") or board.get("latestAvailableDate"))


def _phase18_v7_context_path(date_label: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "warehouse" / "game_context" / f"game_context_{date_label}.csv"


def _phase18_v7_text_key(value: Any) -> str:
    text = _clean(value).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _phase18_v7_team_key(value: Any) -> str:
    key = _phase18_v7_text_key(value)
    if not key:
        return ""
    return _PHASE18_V7_TEAM_ALIASES.get(key, key.upper())


def _phase18_v7_game_context_index(query: dict[str, list[str]], board: dict[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    date_label = _phase18_v7_context_date(query, board)
    path = _phase18_v7_context_path(date_label)
    if not date_label or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            context_rows = list(csv.DictReader(handle))
    except Exception:
        return {}

    index: dict[tuple[str, str], dict[str, str]] = {}
    for context in context_rows:
        team = _phase18_v7_team_key(context.get("team") or context.get("team_abbr") or context.get("teamCode"))
        opponent = _phase18_v7_team_key(context.get("opponent") or context.get("opponent_abbr") or context.get("opponentCode"))
        if team and opponent:
            index[(team, opponent)] = context
    return index


def _phase18_v7_merge_game_context(row: dict[str, Any], index: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    merged = dict(row)
    team = _phase18_v7_team_key(_first(merged, "team", "team_abbr", "teamCode"))
    opponent = _phase18_v7_team_key(_first(merged, "opponent", "opponent_abbr", "opponentCode"))
    context = index.get((team, opponent))
    if not context:
        return merged

    for field in _PHASE18_V7_CONTEXT_FIELDS:
        value = context.get(field)
        if _clean(value):
            merged[field] = value
        alias = _PHASE18_V7_CAMEL_ALIASES.get(field)
        if alias and _clean(value):
            merged[alias] = value

    source = _clean(merged.get("game_context_source"))
    if not source:
        merged["game_context_source"] = "phase18_game_context_join"
    return merged



def _find_snapshot_row(rows: list[dict[str, Any]], query: dict[str, list[str]]) -> dict[str, Any]:
    wanted = {
        "player": _query_value(query, "player").lower(),
        "team": _query_value(query, "team").lower(),
        "opponent": _query_value(query, "opponent").lower(),
        "market": _query_value(query, "market").lower(),
        "line": _query_value(query, "line").lower(),
    }
    for row in rows:
        if all(not expected or _clean(row.get(key)).lower() == expected for key, expected in wanted.items()):
            return dict(row)
    return {}
