from __future__ import annotations

from typing import Any

from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.model_card_service import ModelCardService
from mlb_app.services.picks_service import PicksService

PROP_DETAIL_VERSION = "2026-05-prop-detail-v1"


class PropDetailService:
    """Builds a bettor-facing drilldown for one edge-board prop.

    The detail contract intentionally uses already-pregame fields from the edge
    board/model card layer. It does not reach into postgame grading rows, so the
    page can explain context without introducing prediction-time leakage.
    """

    def __init__(
        self,
        *,
        edge_board_service: EdgeBoardService | None = None,
        model_card_service: ModelCardService | None = None,
        picks_service: PicksService | None = None,
    ) -> None:
        self.edge_board_service = edge_board_service or EdgeBoardService()
        self.model_card_service = model_card_service or ModelCardService()
        self.picks_service = picks_service or PicksService()

    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        lookup = _lookup(query)
        board_query = {
            "season": [lookup.get("season") or "2026"],
            "date": [lookup.get("date")],
            "market": [lookup.get("market")],
            "limit": [lookup.get("limit") or "500"],
            "buildIfMissing": [lookup.get("buildIfMissing") or "1"],
        }
        board_query = {key: value for key, value in board_query.items() if value and value[0]}
        board = self.edge_board_service.payload(board_query)
        row = self._find_row(board.get("rows") or [], lookup)
        if not row:
            row = self._fallback_row(lookup)
        market = _clean(row.get("market") or lookup.get("market"))
        model_card = self._model_card_from_row_or_service(row, market)
        detail = self._build_detail(row, model_card, board, lookup)
        return {
            "status": "ok",
            "version": PROP_DETAIL_VERSION,
            "detail": detail,
            "source": {
                "boardCache": board.get("boardCache") or (board.get("source") or {}).get("boardCache") or {},
                "modelCardSource": model_card.get("source") or "service_fallback",
            },
        }

    def _model_card_from_row_or_service(self, row: dict[str, Any], market: str) -> dict[str, Any]:
        embedded = row.get("modelCard")
        if isinstance(embedded, dict) and embedded:
            card = dict(embedded)
            card.setdefault("market", market)
            card.setdefault("readinessLabel", row.get("readinessLabel"))
            card.setdefault("productionStatus", row.get("productionStatus") or "research_only")
            card.setdefault("canShowConfidentPick", bool(row.get("canShowConfidentPick")))
            card.setdefault("trainingRows", row.get("trainingRows") or 0)
            card.setdefault("positiveRows", row.get("positiveRows") or 0)
            card.setdefault("negativeRows", row.get("negativeRows") or 0)
            card.setdefault("latestGradedDate", row.get("latestGradedDate"))
            card.setdefault("calibration", {"status": row.get("calibrationStatus") or "uncalibrated"})
            card.setdefault("trustWarnings", row.get("trustWarnings") or [])
            card.setdefault("source", "edge_board_row")
            return card
        return self.model_card_service.card_for_market(market) if market else {}

    def _find_row(self, rows: list[Any], lookup: dict[str, str]) -> dict[str, Any]:
        candidates = [row for row in rows if isinstance(row, dict)]
        target_id = _clean(lookup.get("id"))
        if target_id:
            for row in candidates:
                if _clean(row.get("id")) == target_id:
                    return row
        for row in candidates:
            if _matches(row, lookup):
                return row
        return {}

    @staticmethod
    def _fallback_row(lookup: dict[str, str]) -> dict[str, Any]:
        return {
            "id": lookup.get("id") or "prop-detail-fallback",
            "date": lookup.get("date"),
            "player": lookup.get("player"),
            "team": lookup.get("team"),
            "opponent": lookup.get("opponent"),
            "market": lookup.get("market"),
            "marketDisplay": _title(lookup.get("market", "")),
            "line": lookup.get("line"),
            "americanOdds": lookup.get("americanOdds") or lookup.get("odds"),
            "book": lookup.get("book") or "Best available",
            "decisionLabel": lookup.get("decisionLabel") or "No bet",
            "readinessLabel": lookup.get("readinessLabel") or "Research only",
            "confidence": lookup.get("confidence") or "Research",
        }

    def _build_detail(self, row: dict[str, Any], model_card: dict[str, Any], board: dict[str, Any], lookup: dict[str, str]) -> dict[str, Any]:
        probability = _float(_first(row, "modelProbabilityPercent", "finalProbabilityPercent", "probabilityPercent", "probability"))
        odds = _first(row, "americanOdds", "odds", "price")
        implied = _float(_first(row, "impliedProbabilityPercent", "bookImpliedProbabilityPercent", "impliedPercent"))
        if implied is None:
            implied = american_implied_probability(odds)
        edge = _float(_first(row, "edgePercent", "finalEdgePercent", "modelEdgePercent", "edge"))
        if edge is None and probability is not None and implied is not None:
            edge = probability - implied
        fair_odds = probability_to_american(probability)
        warnings = _dedupe(list(row.get("trustWarnings") or []) + list(model_card.get("trustWarnings") or []))
        missing = self._missing_context(row, probability, implied)
        correlation = self._correlation_warnings(row)
        tracking_payload = self._tracking_payload(row, model_card, probability, implied, edge)

        return {
            "id": _clean(row.get("id") or lookup.get("id")),
            "overview": {
                "date": _clean(row.get("date") or lookup.get("date") or board.get("date")),
                "player": _clean(row.get("player")),
                "team": _clean(row.get("team")),
                "opponent": _clean(row.get("opponent")),
                "matchup": _matchup(row),
                "market": _clean(row.get("market")),
                "marketDisplay": _clean(row.get("marketDisplay")) or _title(_clean(row.get("market"))),
                "line": _clean(row.get("line")),
                "americanOdds": _clean(odds),
                "book": _clean(row.get("book")) or "Best available",
                "gameTime": _clean(row.get("gameTime")),
                "decisionLabel": _clean(row.get("decisionLabel")) or "No bet",
                "readinessLabel": _clean(row.get("readinessLabel") or model_card.get("readinessLabel")) or "Research only",
                "confidence": _clean(row.get("confidence")) or "Research",
                "productState": board.get("productState") or {},
                "dataConfidence": board.get("dataConfidence") or "Missing",
            },
            "priceComparison": {
                "bestAvailable": {
                    "book": _clean(row.get("book")) or "Best available",
                    "americanOdds": _clean(odds) or "Not available",
                    "impliedProbabilityPercent": _round(implied),
                },
                "noVigFairEstimate": {
                    "modelProbabilityPercent": _round(probability),
                    "fairAmericanOdds": fair_odds or "Not available",
                    "edgePercent": _round(edge),
                    "note": "Fair price is derived from model probability when available; no-vig market consensus requires multi-book opposite-side prices.",
                },
                "books": self._book_rows(row, odds, implied),
            },
            "modelExplanation": {
                "market": model_card.get("market") or row.get("market"),
                "modelStatus": model_card.get("modelStatus") or "not_ready",
                "productionStatus": model_card.get("productionStatus") or "research_only",
                "canShowConfidentPick": bool(model_card.get("canShowConfidentPick")),
                "trainingRows": int(model_card.get("trainingRows") or row.get("trainingRows") or 0),
                "positiveRows": int(model_card.get("positiveRows") or row.get("positiveRows") or 0),
                "negativeRows": int(model_card.get("negativeRows") or row.get("negativeRows") or 0),
                "latestGradedDate": _clean(model_card.get("latestGradedDate") or row.get("latestGradedDate") or board.get("latestFullyGradedDate")),
                "calibrationStatus": _clean((model_card.get("calibration") or {}).get("status") or row.get("calibrationStatus")) or "uncalibrated",
                "backtest": model_card.get("backtest") or {},
                "decisionPolicy": model_card.get("decisionPolicy") or {},
                "reasons": _detail_reasons(row, probability, implied, edge, model_card),
            },
            "playerContext": {
                "seasonAverage": _context_value(row, "seasonAverage", "seasonAvg", "season_avg", "avg", "battingAverage"),
                "last5": _context_value(row, "last5", "last5Average", "last5Avg", "recent5", "lastFive"),
                "last10": _context_value(row, "last10", "last10Average", "last10Avg", "recent10", "lastTen"),
                "last20": _context_value(row, "last20", "last20Average", "last20Avg", "recent20"),
                "homeAwaySplit": _context_value(row, "homeAwaySplit", "homeAway", "splitHomeAway"),
                "opponentSplit": _context_value(row, "opponentSplit", "vsOpponent", "bvp", "batterVsPitcher"),
                "note": "Unavailable fields mean the current board row did not carry that split into the pregame detail contract.",
            },
            "trendProfile": _trend_profile(row, lookup, board),
            "gameContext": {
                "park": _context_value(row, "park", "venue", "ballpark"),
                "weather": _context_value(row, "weather", "weatherSummary", "weatherContext"),
                "lineupStatus": _context_value(row, "lineupStatus", "lineup", "battingOrder"),
                "probablePitcher": _context_value(row, "pitcher", "probablePitcher", "opposingPitcher"),
                "teamTotal": _context_value(row, "teamTotal", "teamTotalRuns", "impliedTeamTotal"),
                "startTime": _clean(row.get("gameTime")) or "Not available",
            },
            "riskContext": {
                "sampleSize": int(model_card.get("trainingRows") or row.get("trainingRows") or 0),
                "missingData": missing,
                "trustWarnings": warnings,
                "correlationWarnings": correlation,
                "suggestedStake": _clean(row.get("suggestedStake")) or "Research only",
                "exposure": self.picks_service.exposure(),
            },
            "tracking": {
                "separateFromModelBacktests": True,
                "defaultStatus": "Watching",
                "defaultStakeUnits": 0,
                "payload": tracking_payload,
            },
        }

    @staticmethod
    def _book_rows(row: dict[str, Any], odds: Any, implied: float | None) -> list[dict[str, Any]]:
        raw_books = row.get("books") or row.get("bookPrices") or row.get("prices") or []
        books: list[dict[str, Any]] = []
        if isinstance(raw_books, list):
            for item in raw_books:
                if not isinstance(item, dict):
                    continue
                item_odds = _first(item, "americanOdds", "odds", "price")
                books.append(
                    {
                        "book": _clean(_first(item, "book", "sportsbook", "bookmaker")) or "Book",
                        "americanOdds": _clean(item_odds) or "Not available",
                        "impliedProbabilityPercent": _round(american_implied_probability(item_odds)),
                    }
                )
        if not books:
            books.append(
                {
                    "book": _clean(row.get("book")) or "Best available",
                    "americanOdds": _clean(odds) or "Not available",
                    "impliedProbabilityPercent": _round(implied),
                }
            )
        return books[:12]

    @staticmethod
    def _missing_context(row: dict[str, Any], probability: float | None, implied: float | None) -> list[str]:
        checks = {
            "model probability": probability,
            "book implied probability": implied,
            "game time": row.get("gameTime"),
            "line": row.get("line"),
            "book": row.get("book"),
            "latest graded slate": row.get("latestGradedDate"),
        }
        return [label for label, value in checks.items() if value in {None, ""}]

    @staticmethod
    def _correlation_warnings(row: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        if row.get("player"):
            warnings.append("Check exposure to the same player before placing correlated props.")
        if row.get("team") and row.get("opponent"):
            warnings.append("Check game-level exposure before stacking props from this matchup.")
        return warnings

    @staticmethod
    def _tracking_payload(row: dict[str, Any], model_card: dict[str, Any], probability: float | None, implied: float | None, edge: float | None) -> dict[str, Any]:
        return {
            "date": _clean(row.get("date")),
            "player": _clean(row.get("player")),
            "market": _clean(row.get("market")),
            "marketDisplay": _clean(row.get("marketDisplay")) or _title(_clean(row.get("market"))),
            "team": _clean(row.get("team")),
            "opponent": _clean(row.get("opponent")),
            "line": _clean(row.get("line")),
            "americanOdds": _clean(row.get("americanOdds")),
            "book": _clean(row.get("book")) or "Best available",
            "decisionLabel": _clean(row.get("decisionLabel")) or "No bet",
            "readinessLabel": _clean(row.get("readinessLabel") or model_card.get("readinessLabel")) or "Research only",
            "confidence": _clean(row.get("confidence")) or "Research",
            "modelProbabilityPercent": _round(probability),
            "impliedProbabilityPercent": _round(implied),
            "edgePercent": _round(edge),
            "latestGradedDate": _clean(row.get("latestGradedDate") or model_card.get("latestGradedDate")),
            "suggestedStake": _clean(row.get("suggestedStake")) or "Research only",
            "source": "prop_detail",
            "status": "Watching",
            "stakeUnits": 0,
        }


def _lookup(query: dict[str, list[str]]) -> dict[str, str]:
    keys = [
        "id",
        "season",
        "date",
        "market",
        "player",
        "team",
        "opponent",
        "line",
        "americanOdds",
        "odds",
        "book",
        "decisionLabel",
        "readinessLabel",
        "confidence",
        "limit",
        "buildIfMissing",
    ]
    return {key: _query_value(query, key) for key in keys}


def _query_value(query: dict[str, list[str]], name: str, default: str = "") -> str:
    values = query.get(name) or []
    return str(values[0]).strip() if values else default


def _matches(row: dict[str, Any], lookup: dict[str, str]) -> bool:
    for key in ("player", "team", "opponent", "market", "line"):
        wanted = _clean(lookup.get(key)).lower()
        if wanted and _clean(row.get(key)).lower() != wanted:
            return False
    return bool(_clean(lookup.get("player")) or _clean(lookup.get("market")))


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
        text = str(value).strip().replace("%", "")
        return float(text)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _title(value: str) -> str:
    return _clean(value).replace("_", " ").title() or "Market"


def _matchup(row: dict[str, Any]) -> str:
    team = _clean(row.get("team"))
    opponent = _clean(row.get("opponent"))
    return " vs ".join(part for part in (team, opponent) if part) or "Matchup unavailable"


def _context_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            if isinstance(value, (dict, list)):
                return "Available"
            return str(value)
    return "Not available"


def _trend_profile(row: dict[str, Any], lookup: dict[str, str], board: dict[str, Any]) -> dict[str, Any]:
    profile = row.get("hitRates") if isinstance(row.get("hitRates"), dict) else {}
    recent_games = row.get("recentGames") if isinstance(row.get("recentGames"), list) else []

    if not profile or not recent_games:
        try:
            from player_hit_rates import hit_profile_for_row, parse_date
            season = int(_clean(row.get("season") or lookup.get("season") or board.get("season") or "2026"))
            target_date = parse_date(row.get("date") or lookup.get("date") or board.get("date"))
            computed = hit_profile_for_row(row, season, target_date)
            if not profile:
                profile = {
                    "L5": computed.get("L5"),
                    "L10": computed.get("L10"),
                    "L20": computed.get("L20"),
                    "H2H": computed.get("H2H"),
                    "season": computed.get("season"),
                    "prevSeason": computed.get("prevSeason"),
                    "sourceStatus": computed.get("sourceStatus"),
                }
            if not recent_games:
                recent_games = computed.get("recentGames") or []
        except Exception as error:  # noqa: BLE001 - diagnostic only
            profile = dict(profile or {})
            profile.setdefault("sourceStatus", "error")
            profile.setdefault("error", str(error))

    return {
        "windows": profile or {},
        "recentGames": recent_games or [],
        "source": "cached_game_logs",
    }


def american_implied_probability(value: Any) -> float | None:
    try:
        odds = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if odds < 0:
        return abs(odds) / (abs(odds) + 100) * 100
    if odds > 0:
        return 100 / (odds + 100) * 100
    return None


def probability_to_american(probability_percent: float | None) -> str:
    if probability_percent is None or probability_percent <= 0 or probability_percent >= 100:
        return ""
    p = probability_percent / 100
    if p >= 0.5:
        return str(int(round(-(p / (1 - p)) * 100)))
    return f"+{int(round(((1 - p) / p) * 100))}"


def _detail_reasons(row: dict[str, Any], probability: float | None, implied: float | None, edge: float | None, model_card: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if probability is not None and implied is not None:
        reasons.append(f"Model probability {probability:.2f}% versus book-implied {implied:.2f}%.")
    if edge is not None:
        reasons.append(f"Estimated edge is {edge:.2f} percentage points before risk gates.")
    rows = int(model_card.get("trainingRows") or row.get("trainingRows") or 0)
    reasons.append(f"Market sample size: {rows:,} training rows." if rows else "No market-specific sample size is available.")
    status = _clean(model_card.get("readinessLabel") or row.get("readinessLabel")) or "Research only"
    reasons.append(f"Readiness gate: {status}.")
    return reasons[:4]


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
