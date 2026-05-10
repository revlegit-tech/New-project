from __future__ import annotations

from typing import Any

from mlb_app.services.edge_board_service import EdgeBoardService


class FakePlayerboardService:
    def board_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "season": 2026,
            "date": "2026-05-07",
            "top": [
                {
                    "player": "Aaron Judge",
                    "team": "NYY",
                    "opponent": "BAL",
                    "market": "batter_total_bases",
                    "marketDisplay": "Batter Total Bases",
                    "line": "1.5",
                    "americanOdds": "-110",
                    "finalProbabilityPercent": "57.5",
                    "finalEdgePercent": "4.2",
                    "confidence": "Medium",
                }
            ],
            "cardsBuilt": 1,
            "propsLoaded": 1,
            "latestFullyGradedDate": "2026-05-06",
            "dataConfidence": "Partial",
            "trust": {"banner": "Research Mode", "mode": "research_mode"},
            "freshness": {"status": "fresh", "ageSeconds": 120, "snapshotBuiltAt": "2026-05-07T15:00:00Z"},
            "productState": {"state": "research_mode"},
        }


class FakeModelCardService:
    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        return {
            "markets": [self.card_for_market("batter_total_bases")],
            "status": "ok",
        }

    def card_for_market(self, market: str) -> dict[str, Any]:
        return {
            "market": market,
            "readinessLabel": "Research only",
            "productionStatus": "research_only",
            "canShowConfidentPick": False,
            "trainingRows": 190,
            "positiveRows": 54,
            "negativeRows": 136,
            "latestGradedDate": "2026-05-06",
            "calibration": {"status": "uncalibrated"},
            "trustWarnings": ["Probability calibration is not verified."],
        }


def test_edge_board_enriches_playerboard_rows_with_trust_context() -> None:
    payload = EdgeBoardService(
        playerboard_service=FakePlayerboardService(),
        model_card_service=FakeModelCardService(),
    ).payload({"season": ["2026"]})

    assert payload["status"] == "ok"
    assert payload["rowCount"] == 1
    assert payload["summary"]["warningRows"] == 1
    row = payload["rows"][0]
    assert row["decisionLabel"] == "Watchlist"
    assert row["readinessLabel"] == "Research only"
    assert row["trainingRows"] == 190
    assert row["latestGradedDate"] == "2026-05-06"
    assert row["suggestedStake"] == "Research only"
    assert row["trust"]["propIdentity"]["player"] == "Aaron Judge"
    assert row["trust"]["modelEdge"]["edgePercent"] == 4.2
    assert row["trust"]["readiness"]["label"] == "Research only"
    assert row["trust"]["actionability"]["status"] == "watchlist"
    assert row["freshness"]["status"] == "fresh"
    assert row["reasons"]
