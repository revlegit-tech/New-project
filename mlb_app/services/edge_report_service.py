from __future__ import annotations

from collections import Counter
from typing import Any

from mlb_app.config import settings as default_settings
from mlb_app.repositories.research_report_repository import ResearchReportRepository
from mlb_app.services.edge_board_service import EdgeBoardService

EDGE_REPORT_VERSION = "2026-06-edge-report-v1"
EDGE_REPORT_SCHEMA = "edge-report.v1"


class EdgeReportService:
    """Build the sellable daily MLB research report from the existing EdgeBoard.

    This service intentionally consumes ``EdgeBoardService`` instead of reading CSVs
    or building a parallel model path. The report is a product/packaging layer:
    it ranks, buckets, and explains rows that are already governed by the board's
    freshness, model-readiness, and actionability contracts.
    """

    def __init__(
        self,
        *,
        edge_board_service: EdgeBoardService | None = None,
        report_repository: ResearchReportRepository | None = None,
    ) -> None:
        self.edge_board_service = edge_board_service or EdgeBoardService()
        self.report_repository = report_repository

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        report_query = _normalise_query(query or {})
        saved_report = self._payload_from_database(report_query)
        if saved_report is not None:
            return saved_report
        board = self.edge_board_service.payload(report_query)
        rows = [_decorate_row(row) for row in _list_rows(board.get("rows"))]
        ranked = sorted(rows, key=lambda item: item["score"], reverse=True)
        fades = sorted(rows, key=lambda item: (_edge(item), item["score"]))
        sections = [
            _section(
                key="free_preview",
                title="Free Preview",
                description="A small teaser that can be posted publicly without giving away the full paid board.",
                cards=_limit([item for item in ranked if _edge(item) > 0], 3),
                publishTier="free",
            ),
            _section(
                key="straight_card",
                title="Best Straight Props",
                description="Highest risk-adjusted props after model edge, readiness, and freshness gates.",
                cards=_limit([item for item in ranked if item["riskBucket"] in {"Core", "Standard"}], 8),
            ),
            _section(
                key="home_run_targets",
                title="HR Targets",
                description="Power-market candidates only. These remain research-first because HR props are high variance.",
                cards=_limit([item for item in ranked if _is_home_run(item)], 8),
            ),
            _section(
                key="strikeout_props",
                title="Strikeout Props",
                description="Pitcher K props bucketed by edge, opponent context already present on the board, and readiness.",
                cards=_limit([item for item in ranked if _is_strikeout(item)], 8),
            ),
            _section(
                key="total_bases",
                title="Total Bases",
                description="Batter total-bases props with enough price/model signal to deserve manual review.",
                cards=_limit([item for item in ranked if _is_total_bases(item)], 8),
            ),
            _section(
                key="value_watchlist",
                title="Plus-Money Value Watchlist",
                description="Positive-edge plus-money rows for users who want value candidates instead of safest prices.",
                cards=_limit([item for item in ranked if _edge(item) > 0 and _american_odds(item) >= 100], 8),
            ),
            _section(
                key="lotto_builder",
                title="Lotto Builder",
                description="High-upside rows for parlays/ladders. They are explicitly not marked as safe straight bets.",
                cards=_limit(_lotto_candidates(ranked), 6),
            ),
            _section(
                key="fades",
                title="Fade / Avoid",
                description="Rows that do not clear the current model-edge or trust threshold.",
                cards=_limit([item for item in fades if _edge(item) <= 0 or item["decisionLabel"].lower() == "no bet"], 8),
            ),
        ]
        return {
            "status": "ok",
            "schemaVersion": EDGE_REPORT_SCHEMA,
            "version": EDGE_REPORT_VERSION,
            "date": board.get("date"),
            "season": board.get("season"),
            "product": {
                "name": "RevLegit MLB Edge",
                "positioning": "MLB-only prop research report generated from the production EdgeBoard.",
                "delivery": ["Free preview", "Paid daily board", "Discord-ready report", "Dashboard drilldown"],
                "disclaimer": "Research only. No guaranteed outcomes. Use responsible bankroll rules and verify sportsbook lines before acting.",
            },
            "summary": _summary(rows, board),
            "sections": sections,
            "pricing": {
                "starterMonthlyUsd": 29,
                "premiumMonthlyUsd": 79,
                "vipMonthlyUsd": 149,
                "note": "Pricing metadata is for packaging the product offer; it does not change board logic or picks tracking.",
            },
            "publishPlan": _publish_plan(),
            "trust": board.get("trust", {}),
            "freshness": board.get("freshness", {}),
            "source": {
                "boardVersion": board.get("version"),
                "rowCount": board.get("rowCount", len(rows)),
                "boardCache": board.get("boardCache", {}),
                "boardSource": board.get("source", {}),
            },
            "meta": {
                "generatedFrom": "/api/edge-board",
                "requestLimit": int(report_query.get("limit", ["5000"])[0]),
                "researchOnly": True,
            },
        }

    def _payload_from_database(self, query: dict[str, list[str]]) -> dict[str, Any] | None:
        if self.report_repository is None:
            return None
        try:
            season = _int((query.get("season") or [default_settings.current_season])[0], default_settings.current_season)
            date_label = _clean((query.get("date") or [""])[0])
            return self.report_repository.latest_payload(season=season, date_label=date_label)
        except Exception:
            return None


def _normalise_query(query: dict[str, list[str]]) -> dict[str, list[str]]:
    normalised = {str(key): [str(item) for item in values] for key, values in query.items()}
    normalised.setdefault("season", [str(default_settings.current_season)])
    normalised.setdefault("limit", ["5000"])
    return normalised


def _list_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _decorate_row(row: dict[str, Any]) -> dict[str, Any]:
    edge = _number(_first(row, "edgePercent", "finalEdgePercent", "edge"))
    model_probability = _number(_first(row, "modelProbabilityPercent", "finalProbabilityPercent", "probability"))
    implied_probability = _number(_first(row, "impliedProbabilityPercent", "sportsbookImpliedPercent", "impliedPercent"))
    odds = _american_odds(row)
    score = _score(row, edge=edge, model_probability=model_probability, implied_probability=implied_probability, odds=odds)
    grade = _grade(score)
    risk_bucket = _risk_bucket(row, score=score, edge=edge, odds=odds)
    warnings = [_clean(item) for item in row.get("trustWarnings") or [] if _clean(item)]
    reasons = [_clean(item) for item in row.get("reasons") or [] if _clean(item)]
    generated_reasons = _generated_reasons(row, score=score, grade=grade, edge=edge, odds=odds, risk_bucket=risk_bucket)
    return {
        "id": _clean(row.get("id")),
        "propKey": _clean(row.get("propKey")),
        "player": _clean(_first(row, "player", "playerName", "team")),
        "team": _clean(row.get("team")),
        "opponent": _clean(row.get("opponent")),
        "matchup": _matchup(row),
        "market": _clean(row.get("market")),
        "marketDisplay": _clean(row.get("marketDisplay")) or _title(_clean(row.get("market"))),
        "side": _clean(_first(row, "side", "rawLabel", "pickSide")) or _clean(((row.get("trust") or {}).get("propIdentity") or {}).get("side")) or "Over",
        "line": _clean(row.get("line")),
        "americanOdds": _clean(_first(row, "americanOdds", "odds", "price")),
        "book": _clean(row.get("book")) or "Best available",
        "score": score,
        "grade": grade,
        "riskBucket": risk_bucket,
        "confidence": _clean(row.get("confidence")) or "Research",
        "edgePercent": round(edge, 2),
        "modelProbabilityPercent": round(model_probability, 2) if model_probability else None,
        "impliedProbabilityPercent": round(implied_probability, 2) if implied_probability else None,
        "decisionLabel": _clean(row.get("decisionLabel")) or "Watchlist",
        "readinessLabel": _clean(row.get("readinessLabel")) or "Research only",
        "suggestedStake": "Research only" if risk_bucket != "Fade" else "0u",
        "sourceRowRank": _int(row.get("rank"), 0),
        "freshness": row.get("freshness") if isinstance(row.get("freshness"), dict) else {},
        "trust": row.get("trust") if isinstance(row.get("trust"), dict) else {},
        "reasons": _dedupe(reasons + generated_reasons)[:5],
        "warnings": warnings[:5],
    }


def _section(*, key: str, title: str, description: str, cards: list[dict[str, Any]], publishTier: str = "premium") -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "description": description,
        "publishTier": publishTier,
        "cardCount": len(cards),
        "cards": cards,
        "emptyState": "No rows cleared this section's filter from the current EdgeBoard." if not cards else "",
    }


def _summary(rows: list[dict[str, Any]], board: dict[str, Any]) -> dict[str, Any]:
    markets = Counter(_clean(row.get("market")) or "unknown" for row in rows)
    grades = Counter(_clean(row.get("grade")) or "NA" for row in rows)
    buckets = Counter(_clean(row.get("riskBucket")) or "Research" for row in rows)
    return {
        "rowCount": len(rows),
        "positiveEdgeRows": sum(1 for row in rows if _edge(row) > 0),
        "coreRows": buckets.get("Core", 0),
        "standardRows": buckets.get("Standard", 0),
        "lottoRows": buckets.get("Lotto", 0),
        "fadeRows": buckets.get("Fade", 0),
        "markets": dict(markets.most_common(12)),
        "grades": dict(sorted(grades.items())),
        "riskBuckets": dict(buckets),
        "boardDataConfidence": board.get("dataConfidence", "Missing"),
        "latestFullyGradedDate": board.get("latestFullyGradedDate", ""),
    }


def _publish_plan() -> list[dict[str, str]]:
    return [
        {"step": "Free preview", "cadence": "Daily morning", "copy": "Post one HR/K/TB teaser with reasoning and no guarantee language."},
        {"step": "Paid board", "cadence": "After lineup/odds review", "copy": "Publish full sections, fades, and confidence grades to paid members."},
        {"step": "Final update", "cadence": "1-2 hours before first pitch", "copy": "Refresh lines, scratches, and weather flags before users act."},
        {"step": "Results tracker", "cadence": "After games finish", "copy": "Grade all official research picks honestly, including losses and CLV notes."},
    ]


def _score(row: dict[str, Any], *, edge: float, model_probability: float, implied_probability: float, odds: int) -> int:
    score = 50.0
    score += max(-25.0, min(35.0, edge * 3.0))
    if model_probability and implied_probability:
        score += max(-8.0, min(8.0, (model_probability - implied_probability) * 0.5))
    confidence = _clean(row.get("confidence")).lower()
    if "high" in confidence:
        score += 8
    elif "medium" in confidence:
        score += 5
    elif "low" in confidence:
        score -= 3
    decision = _clean(row.get("decisionLabel")).lower()
    if decision == "potential edge":
        score += 8
    elif decision == "model lean":
        score += 5
    elif decision == "watchlist":
        score += 2
    elif decision == "no bet":
        score -= 18
    readiness = _clean(row.get("readinessLabel")).lower()
    if "production" in readiness or "ready" in readiness:
        score += 6
    elif "research" in readiness:
        score -= 2
    freshness = row.get("freshness") if isinstance(row.get("freshness"), dict) else {}
    freshness_status = _clean(freshness.get("status")).lower()
    if freshness_status == "fresh":
        score += 4
    elif freshness_status in {"stale", "missing"}:
        score -= 10
    if odds >= 350:
        score -= 7
    elif odds >= 180:
        score -= 3
    return int(max(0, min(100, round(score))))


def _grade(score: int) -> str:
    if score >= 88:
        return "A+"
    if score >= 78:
        return "A"
    if score >= 68:
        return "B"
    if score >= 58:
        return "C"
    return "D"


def _risk_bucket(row: dict[str, Any], *, score: int, edge: float, odds: int) -> str:
    market = _clean(row.get("market")).lower()
    decision = _clean(row.get("decisionLabel")).lower()
    if edge <= 0 or decision == "no bet" or score < 48:
        return "Fade"
    if "home_run" in market or odds >= 180:
        return "Lotto"
    if score >= 78 and edge >= 5:
        return "Core"
    return "Standard"


def _generated_reasons(row: dict[str, Any], *, score: int, grade: str, edge: float, odds: int, risk_bucket: str) -> list[str]:
    reasons = [f"Report grade {grade} ({score}/100) after edge, trust, odds, and freshness adjustments."]
    if edge > 0:
        reasons.append(f"Positive modeled edge is visible at +{edge:.2f} percentage points.")
    else:
        reasons.append("Modeled edge is non-positive, so this belongs in the fade/avoid workflow.")
    if risk_bucket == "Lotto":
        reasons.append("High-variance bucket; better suited for small-stake ladders/parlays than core straight play.")
    elif risk_bucket == "Core":
        reasons.append("Clears the strongest score bucket, but the app still labels it research-only until user review.")
    if odds:
        reasons.append(f"Current American odds captured as {_format_odds(odds)}; users should verify live book price before publishing.")
    return reasons


def _lotto_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["riskBucket"] == "Lotto" and _edge(row) > 0]


def _limit(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return rows[: max(0, limit)]


def _is_home_run(row: dict[str, Any]) -> bool:
    market = _clean(row.get("market")).lower()
    return "home_run" in market or "homer" in market


def _is_strikeout(row: dict[str, Any]) -> bool:
    return "strikeout" in _clean(row.get("market")).lower()


def _is_total_bases(row: dict[str, Any]) -> bool:
    return "total_bases" in _clean(row.get("market")).lower()


def _edge(row: dict[str, Any]) -> float:
    return _number(row.get("edgePercent"))


def _american_odds(row: dict[str, Any]) -> int:
    return _int(_first(row, "americanOdds", "odds", "price"), 0)


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _number(value: Any) -> float:
    try:
        if value in {None, ""}:
            return 0.0
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any, fallback: int) -> int:
    try:
        if value in {None, ""}:
            return fallback
        return int(float(str(value).replace("+", "")))
    except (TypeError, ValueError):
        return fallback


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _title(value: str) -> str:
    return _clean(value).replace("_", " ").title() or "Market"


def _matchup(row: dict[str, Any]) -> str:
    team = _clean(row.get("team"))
    opponent = _clean(row.get("opponent"))
    return f"{team} @ {opponent}" if team and opponent else _clean(row.get("game") or row.get("matchup")) or "Matchup pending"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _format_odds(odds: int) -> str:
    return f"+{odds}" if odds > 0 else str(odds)
