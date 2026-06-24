from __future__ import annotations

from typing import Any

from mlb_app.api.models import EdgeBoardRow, ResearchReportCard
from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.edge_report_service import EdgeReportService


class FakePlayerboardService:
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
                }
            ],
            "cardsBuilt": 1,
            "propsLoaded": 1,
            "latestFullyGradedDate": "2026-06-23",
            "dataConfidence": "Good",
            "trust": {
                "runtimeReadiness": {
                    "collectorStatus": "ok",
                    "dataSourceCapabilityStatus": "ok",
                    "featureStoreReady": True,
                    "readyForBoard": True,
                    "readyForBaselineTraining": False,
                    "readyForProductionTraining": False,
                    "missingFeatureGroups": [],
                }
            },
            "freshness": {"status": "fresh", "ageSeconds": 120, "snapshotBuiltAt": "2026-06-24T12:00:00Z"},
            "productState": {"state": "research_mode"},
        }


class FakeModelCardService:
    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        return {"markets": [self.card_for_market("batter_total_bases")], "status": "ok"}

    def card_for_market(self, market: str) -> dict[str, Any]:
        return {
            "market": market,
            "readinessLabel": "Research only",
            "productionStatus": "research_only",
            "productionReady": False,
            "canShowConfidentPick": False,
            "trainingRows": 100,
            "positiveRows": 50,
            "negativeRows": 50,
            "latestGradedDate": "2026-06-23",
            "calibration": {"status": "uncalibrated"},
            "trustWarnings": ["Production training is not eligible."],
        }


class FakeEdgeBoardService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "edge-board.test",
            "season": 2026,
            "date": "2026-06-24",
            "rowCount": 1,
            "rows": [
                {
                    "id": "row-1",
                    "propKey": "row-1",
                    "player": "Aaron Judge",
                    "team": "NYY",
                    "opponent": "BAL",
                    "market": "batter_total_bases",
                    "marketDisplay": "Batter Total Bases",
                    "side": "Over",
                    "line": "1.5",
                    "americanOdds": "-110",
                    "book": "TestBook",
                    "edgePercent": "4.2",
                    "modelProbabilityPercent": "57.5",
                    "impliedProbabilityPercent": "52.38",
                    "decisionLabel": "Watchlist",
                    "actionLabel": "Research only",
                    "readinessLabel": "Research only",
                    "marketCapabilityStatus": "model_supported",
                    "modelProductionEligible": False,
                    "rank": 1,
                    "freshness": {"status": "fresh"},
                    "trust": {"actionLabel": "Research only", "marketCapabilityStatus": "model_supported"},
                    "reasons": ["Model production eligibility is not confirmed."],
                    "trustWarnings": [],
                }
            ],
            "trust": {
                "runtimeReadiness": {
                    "collectorStatus": "ok",
                    "dataSourceCapabilityStatus": "ok",
                    "featureStoreReady": True,
                    "readyForBoard": True,
                    "readyForBaselineTraining": False,
                    "readyForProductionTraining": False,
                    "missingFeatureGroups": [],
                }
            },
            "freshness": {"status": "fresh"},
            "source": {},
            "boardCache": {},
        }


def test_edge_board_contract_exposes_safe_action_and_readiness_fields() -> None:
    payload = EdgeBoardService(playerboard_service=FakePlayerboardService(), model_card_service=FakeModelCardService()).payload({"season": ["2026"]})
    row = payload["rows"][0]

    assert row["marketCapabilityStatus"] == "model_supported"
    assert row["actionLabel"] in {"No bet", "Watchlist", "Model lean", "Research only", "Data stale", "Unsupported market"}
    assert row["modelProductionEligible"] is False
    assert payload["trust"]["runtimeReadiness"]["featureStoreReady"] is True


def test_report_includes_data_source_and_model_readiness_trust_fields() -> None:
    payload = EdgeReportService(edge_board_service=FakeEdgeBoardService()).payload({"date": ["2026-06-24"], "limit": ["10"]})  # type: ignore[arg-type]

    readiness = payload["trust"]["runtimeReadiness"]
    assert readiness["collectorStatus"] == "ok"
    assert readiness["dataSourceCapabilityStatus"] == "ok"
    assert readiness["featureStoreReady"] is True
    assert readiness["readyForBoard"] is True
    assert readiness["readyForBaselineTraining"] is False
    assert readiness["readyForProductionTraining"] is False
    card = payload["sections"][0]["cards"][0]
    assert card["actionLabel"] == "Research only"
    assert card["marketCapabilityStatus"] == "model_supported"
    assert card["modelProductionEligible"] is False
    assert any("production eligibility is not confirmed" in reason.lower() for reason in card["reasons"])


def test_strict_board_and_report_models_support_sprint30_labels() -> None:
    board = EdgeBoardRow.model_validate(
        {
            "player": "A",
            "team": "NYY",
            "opponent": "BAL",
            "market": "batter_total_bases",
            "decisionLabel": "Watchlist",
            "actionLabel": "Model lean",
            "marketCapabilityStatus": "model_supported",
            "modelProductionEligible": False,
        }
    )
    report = ResearchReportCard.model_validate(
        {
            "id": "1",
            "propKey": "1",
            "player": "A",
            "team": "NYY",
            "opponent": "BAL",
            "market": "batter_total_bases",
            "decisionLabel": "Watchlist",
            "actionLabel": "Research only",
            "marketCapabilityStatus": "model_supported",
            "modelProductionEligible": False,
        }
    )

    assert board.actionLabel == "Model lean"
    assert report.actionLabel == "Research only"
