from __future__ import annotations

from typing import Any

from mlb_app.services.prop_detail_service import PropDetailService, american_implied_probability, probability_to_american


class FakeEdgeBoardService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "status": "ok",
            "date": "2026-05-07",
            "latestFullyGradedDate": "2026-05-06",
            "dataConfidence": "Partial",
            "productState": {"state": "research_mode"},
            "rows": [
                {
                    "id": "judge-total-bases",
                    "date": "2026-05-07",
                    "player": "Aaron Judge",
                    "team": "NYY",
                    "opponent": "BAL",
                    "market": "batter_total_bases",
                    "marketDisplay": "Batter Total Bases",
                    "line": "1.5",
                    "americanOdds": "+115",
                    "book": "Book A",
                    "gameTime": "7:05 PM",
                    "decisionLabel": "Watchlist",
                    "readinessLabel": "Research only",
                    "confidence": "Medium",
                    "modelProbabilityPercent": "54.50",
                    "impliedProbabilityPercent": "46.51",
                    "edgePercent": "7.99",
                    "trainingRows": 190,
                    "latestGradedDate": "2026-05-06",
                    "trustWarnings": ["Probability calibration is not verified."],
                    "pitcher": "Corbin Burnes",
                    "park": "Yankee Stadium",
                    "weatherSummary": "Mild wind out",
                }
            ],
        }


class FakeModelCardService:
    def card_for_market(self, market: str) -> dict[str, Any]:
        return {
            "market": market,
            "modelStatus": "ready",
            "productionStatus": "research_only",
            "readinessLabel": "Research only",
            "canShowConfidentPick": False,
            "trainingRows": 190,
            "positiveRows": 54,
            "negativeRows": 136,
            "latestGradedDate": "2026-05-06",
            "calibration": {"status": "uncalibrated"},
            "backtest": {"roiPercent": -39.18, "winRatePercent": 31.56},
            "trustWarnings": ["Recent market-level ROI is negative."],
            "decisionPolicy": {"primaryLabel": "No bet"},
        }


class FakePicksService:
    def exposure(self) -> dict[str, Any]:
        return {"activePickCount": 1, "totalStakeUnits": 0.25, "warnings": []}


def test_prop_detail_builds_price_model_context_and_tracking_payload() -> None:
    payload = PropDetailService(
        edge_board_service=FakeEdgeBoardService(),
        model_card_service=FakeModelCardService(),
        picks_service=FakePicksService(),
    ).payload({"id": ["judge-total-bases"], "market": ["batter_total_bases"]})

    assert payload["status"] == "ok"
    detail = payload["detail"]
    assert detail["overview"]["player"] == "Aaron Judge"
    assert detail["priceComparison"]["bestAvailable"]["americanOdds"] == "+115"
    assert detail["priceComparison"]["noVigFairEstimate"]["fairAmericanOdds"] == "-120"
    assert detail["modelExplanation"]["trainingRows"] == 190
    assert detail["riskContext"]["exposure"]["activePickCount"] == 1
    assert detail["tracking"]["separateFromModelBacktests"] is True
    assert detail["tracking"]["payload"]["source"] == "prop_detail"
    assert detail["tracking"]["payload"]["stakeUnits"] == 0


def test_prop_detail_can_fallback_from_query_without_edge_row() -> None:
    payload = PropDetailService(
        edge_board_service=FakeEdgeBoardService(),
        model_card_service=FakeModelCardService(),
        picks_service=FakePicksService(),
    ).payload({"player": ["Missing Player"], "market": ["batter_hits"], "team": ["NYY"], "opponent": ["BAL"]})

    detail = payload["detail"]
    assert detail["overview"]["player"] == "Missing Player"
    assert detail["overview"]["readinessLabel"] == "Research only"
    assert "model probability" in detail["riskContext"]["missingData"]


def test_american_odds_helpers() -> None:
    assert round(american_implied_probability("-110") or 0, 2) == 52.38
    assert round(american_implied_probability("+150") or 0, 2) == 40.0
    assert probability_to_american(60) == "-150"
    assert probability_to_american(40) == "+150"

class ExplodingModelCardService:
    def card_for_market(self, market: str) -> dict[str, Any]:
        raise AssertionError("PropDetailService should reuse the embedded board-row modelCard")


class EmbeddedModelCardEdgeBoardService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        payload = FakeEdgeBoardService().payload(query)
        payload["boardCache"] = {"hit": True, "reason": "hit"}
        payload["rows"][0]["modelCard"] = {
            "market": "batter_total_bases",
            "modelStatus": "ready",
            "productionStatus": "research_only",
            "readinessLabel": "Research only",
            "canShowConfidentPick": False,
            "trainingRows": 190,
            "positiveRows": 54,
            "negativeRows": 136,
            "latestGradedDate": "2026-05-06",
            "calibration": {"status": "uncalibrated"},
            "backtest": {"roiPercent": -39.18, "winRatePercent": 31.56},
            "trustWarnings": ["Recent market-level ROI is negative."],
            "decisionPolicy": {"primaryLabel": "No bet"},
        }
        return payload


def test_prop_detail_reuses_embedded_model_card_from_cached_board_row() -> None:
    payload = PropDetailService(
        edge_board_service=EmbeddedModelCardEdgeBoardService(),
        model_card_service=ExplodingModelCardService(),
        picks_service=FakePicksService(),
    ).payload({"id": ["judge-total-bases"], "market": ["batter_total_bases"]})

    assert payload["source"]["boardCache"]["hit"] is True
    assert payload["source"]["modelCardSource"] == "edge_board_row"
    assert payload["detail"]["modelExplanation"]["backtest"]["roiPercent"] == -39.18
