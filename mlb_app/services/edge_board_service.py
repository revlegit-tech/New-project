from __future__ import annotations

from pathlib import Path
from typing import Any, Hashable

from mlb_app.services.board_cache import BoardCache, BoardCacheBuildResult
from mlb_app.services.model_card_service import ModelCardService
from mlb_app.services.playerboard_service import PlayerboardService

EDGE_BOARD_VERSION = "2026-05-edge-board-v1"
DEFAULT_BOARD_CACHE = BoardCache(ttl_seconds=30.0)


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
    ) -> None:
        self.playerboard_service = playerboard_service or PlayerboardService()
        self.model_card_service = model_card_service or ModelCardService()
        self.board_cache = board_cache or DEFAULT_BOARD_CACHE
        self._cards: dict[str, dict[str, Any]] = {}

    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        cache_key = _board_cache_key(query)
        dependency_paths = _playerboard_dependency_paths(query)

        # Explicit refresh/save requests are operator-intent paths. Do not serve
        # them from cache, but store the fresh result for subsequent normal reads.
        if _bypass_board_cache(query):
            payload = self._build_payload(query)
            result = self.board_cache.set(cache_key, payload, dependency_paths=dependency_paths)
            return self._with_board_cache_metadata(result, served_from_cache=False, reason="bypass_refresh_or_save")

        result = self.board_cache.get_or_build(
            cache_key,
            lambda: self._build_payload(query),
            dependency_paths=dependency_paths,
        )
        return self._with_board_cache_metadata(result, served_from_cache=result.hit, reason=result.reason)

    def _build_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        board = self.playerboard_service.board_payload(query)
        raw_rows = _list_rows(board.get("top") or board.get("rows") or [])
        self._cards = self._load_cards()
        rows = [self._enrich_row(row, index + 1, board) for index, row in enumerate(raw_rows)]

        return {
            "status": "ok",
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
            },
            "filters": self._filter_options(rows),
            "summary": self._summary(rows),
            "trust": board.get("trust", {}),
            "productState": board.get("productState"),
            "latestFullyGradedDate": board.get("latestFullyGradedDate", ""),
            "dataConfidence": board.get("dataConfidence", "Missing"),
            "modelReadiness": board.get("modelReadiness", {}),
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

        enriched = dict(row)
        enriched.update(
            {
                "id": _row_id(row, rank),
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
            }
        )
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


def _board_cache_key(query: dict[str, list[str]]) -> Hashable:
    season = _int_query(query, "season", 2026)
    date_label = _query_value(query, "date")
    market = _query_value(query, "market").lower()
    limit = _int_query(query, "limit", 50)
    return (EDGE_BOARD_VERSION, season, date_label, market, limit)


def _playerboard_dependency_paths(query: dict[str, list[str]]) -> tuple[Path, ...]:
    season = _int_query(query, "season", 2026)
    try:
        from playerboard import playerboard_file
    except Exception:
        return ()
    return (Path(playerboard_file(season)),)


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
