from __future__ import annotations

from typing import Any

from mlb_app.services.edge_report_service import EdgeReportService


class FakeEdgeBoardService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "edge-board-test",
            "season": 2026,
            "date": "2026-06-21",
            "rowCount": 4,
            "dataConfidence": "Partial",
            "latestFullyGradedDate": "2026-06-20",
            "trust": {"mode": "research_mode"},
            "freshness": {"status": "fresh", "ageSeconds": 120},
            "rows": [
                {
                    "id": "judge-hr",
                    "propKey": "judge-hr-key",
                    "rank": 1,
                    "player": "Aaron Judge",
                    "team": "NYY",
                    "opponent": "BOS",
                    "market": "batter_home_runs",
                    "marketDisplay": "Batter Home Runs",
                    "line": "0.5",
                    "americanOdds": "+360",
                    "book": "Best available",
                    "finalProbabilityPercent": "24.0",
                    "impliedProbabilityPercent": "21.7",
                    "edgePercent": "6.5",
                    "confidence": "Medium",
                    "decisionLabel": "Watchlist",
                    "readinessLabel": "Research only",
                    "freshness": {"status": "fresh"},
                    "reasons": ["Model price is 6.50 percentage points above the book-implied price."],
                    "trustWarnings": ["High-variance market."],
                },
                {
                    "id": "cole-k",
                    "rank": 2,
                    "player": "Gerrit Cole",
                    "team": "NYY",
                    "opponent": "BOS",
                    "market": "pitcher_strikeouts",
                    "marketDisplay": "Pitcher Strikeouts",
                    "line": "5.5",
                    "americanOdds": "-115",
                    "finalProbabilityPercent": "61.0",
                    "impliedProbabilityPercent": "53.5",
                    "edgePercent": "7.5",
                    "confidence": "High",
                    "decisionLabel": "Model lean",
                    "readinessLabel": "Research only",
                    "freshness": {"status": "fresh"},
                },
                {
                    "id": "soto-tb",
                    "rank": 3,
                    "player": "Juan Soto",
                    "team": "NYY",
                    "opponent": "BOS",
                    "market": "batter_total_bases",
                    "marketDisplay": "Batter Total Bases",
                    "line": "1.5",
                    "americanOdds": "+120",
                    "finalProbabilityPercent": "55.0",
                    "impliedProbabilityPercent": "45.5",
                    "edgePercent": "5.2",
                    "confidence": "Medium",
                    "decisionLabel": "Watchlist",
                    "readinessLabel": "Research only",
                    "freshness": {"status": "fresh"},
                },
                {
                    "id": "bad-price",
                    "rank": 4,
                    "player": "Bad Price",
                    "team": "BOS",
                    "opponent": "NYY",
                    "market": "batter_hits",
                    "marketDisplay": "Batter Hits",
                    "line": "0.5",
                    "americanOdds": "-220",
                    "edgePercent": "-3.0",
                    "confidence": "Low",
                    "decisionLabel": "No bet",
                    "readinessLabel": "Research only",
                    "freshness": {"status": "fresh"},
                },
            ],
        }


def test_edge_report_packages_board_into_paid_research_sections() -> None:
    payload = EdgeReportService(edge_board_service=FakeEdgeBoardService()).payload({"date": ["2026-06-21"]})

    assert payload["status"] == "ok"
    assert payload["schemaVersion"] == "edge-report.v1"
    assert payload["product"]["name"] == "RevLegit MLB Edge"
    assert payload["summary"]["rowCount"] == 4
    assert payload["summary"]["positiveEdgeRows"] == 3
    sections = {section["key"]: section for section in payload["sections"]}
    assert sections["free_preview"]["publishTier"] == "free"
    assert sections["home_run_targets"]["cards"][0]["player"] == "Aaron Judge"
    assert sections["strikeout_props"]["cards"][0]["player"] == "Gerrit Cole"
    assert sections["total_bases"]["cards"][0]["player"] == "Juan Soto"
    assert sections["fades"]["cards"][0]["player"] == "Bad Price"
    assert all(card["suggestedStake"] in {"Research only", "0u"} for section in payload["sections"] for card in section["cards"])
