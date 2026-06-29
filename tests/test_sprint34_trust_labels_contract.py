from __future__ import annotations

from typing import Any

from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.edge_report_service import EdgeReportService


class Sprint34PlayerboardService:
    def board_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "season": 2026,
            "date": "2026-06-24",
            "top": [
                {
                    "player": "Aaron Judge",
                    "team": "NYY",
                    "opponent": "BAL",
                    "market": "batter_total_bases",
                    "line": "1.5",
                    "americanOdds": "-110",
                    "finalProbabilityPercent": "57.5",
                    "finalEdgePercent": "4.2",
                    "confidence": "Medium",
                    "missingFeatureGroups": ["umpire"],
                    "game_market_available": False,
                    "game_market_enrichment_status": "warehouse_unavailable",
                }
            ],
            "cardsBuilt": 1,
            "propsLoaded": 1,
            "latestFullyGradedDate": "2026-06-23",
            "dataConfidence": "Good",
            "trust": {
                "runtimeReadiness": {
                    "collectorStatus": "ok",
                    "dataSourceCapabilityStatus": "partial",
                    "featureStoreReady": True,
                    "readyForBoard": True,
                    "readyForBaselineTraining": True,
                    "readyForProductionTraining": False,
                    "missingFeatureGroups": ["umpire"],
                }
            },
            "freshness": {"status": "fresh", "ageSeconds": 120, "snapshotBuiltAt": "2026-06-24T12:00:00Z"},
            "modelReadiness": {
                "eligibleBaselineMarkets": ["batter_total_bases"],
                "eligibleProductionMarkets": [],
            },
            "productState": {"state": "research_mode"},
        }


class Sprint34ModelCardService:
    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        return {"markets": [self.card_for_market("batter_total_bases")], "status": "ok"}

    def card_for_market(self, market: str) -> dict[str, Any]:
        return {
            "market": market,
            "readinessLabel": "Research only",
            "productionStatus": "baseline_trained",
            "productionReady": False,
            "canShowConfidentPick": False,
            "trainingRows": 100,
            "positiveRows": 50,
            "negativeRows": 50,
            "latestGradedDate": "2026-06-23",
            "calibration": {"status": "missing"},
            "backtest": {"status": "missing"},
            "trustWarnings": ["Production training is not eligible."],
        }


def test_edge_board_rows_expose_sprint34_trust_visibility_fields() -> None:
    payload = EdgeBoardService(
        playerboard_service=Sprint34PlayerboardService(),
        model_card_service=Sprint34ModelCardService(),
    ).payload({"season": ["2026"]})

    row = payload["rows"][0]

    assert row["actionLabel"] in {"Research only", "Watchlist", "No bet"}
    assert row["marketCapabilityStatus"] == "model_supported"
    assert row["modelProductionEligible"] is False
    assert row["productionStatus"] == "baseline_trained"
    assert row["calibrationStatus"] == "missing"
    assert row["backtestStatus"] == "missing"
    assert row["missingDataCount"] == 1
    assert row["warningCount"] == 1
    assert row["suggestedStake"] in {"Research only", "0u"}
    assert row["trust"]["actionability"]["stakeUnits"] == 0
    assert "Calibration needed" in row["actionabilityReason"]


def test_report_payload_includes_readiness_summary_without_changing_gates() -> None:
    board_service = EdgeBoardService(
        playerboard_service=Sprint34PlayerboardService(),
        model_card_service=Sprint34ModelCardService(),
    )

    payload = EdgeReportService(edge_board_service=board_service).payload({"date": ["2026-06-24"], "limit": ["10"]})

    assert payload["summary"]["eligibleBaselineMarkets"] == ["batter_total_bases"]
    assert payload["summary"]["eligibleProductionMarkets"] == []
    assert payload["summary"]["productionEligibleRows"] == 0
    assert payload["summary"]["missingDataRows"] == 1
    assert payload["summary"]["calibrationStatusCounts"]["missing"] == 1
    assert payload["summary"]["backtestStatusCounts"]["missing"] == 1
    card = payload["sections"][0]["cards"][0]
    assert card["modelProductionEligible"] is False
    assert card["calibrationStatus"] == "missing"
    assert card["backtestStatus"] == "missing"
