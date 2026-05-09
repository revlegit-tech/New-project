from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from mlb_app.services.prop_detail_service import PropDetailService, american_implied_probability, probability_to_american


class FakeHealth:
    def to_dict(self) -> dict[str, Any]:
        return {
            "dataConfidence": "Partial",
            "latestFullyGradedDate": "2026-05-06",
            "freshness": {"label": "fresh"},
        }


class FakeSnapshot:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.season = 2026
        self.date = "2026-05-07"
        self.rows = tuple(rows)
        self.product_state = {"state": "research_mode"}
        self.health = FakeHealth()
        self.cache_hit = True
        self.file_signature = SimpleNamespace(exists=True)
        self._prop_index = {str(row.get("propKey")): dict(row) for row in rows if row.get("propKey")}
        self.row_for_prop_key_calls: list[str] = []

    def row_for_prop_key(self, prop_key: str) -> dict[str, Any]:
        self.row_for_prop_key_calls.append(prop_key)
        return dict(self._prop_index.get(prop_key) or {})

    def source_meta(self) -> dict[str, Any]:
        return {"file": "fixture.csv", "rows": len(self.rows), "snapshotSignature": "fixture:1"}


class FakeReadService:
    def __init__(self, snapshot: FakeSnapshot) -> None:
        self.snapshot = snapshot
        self.queries: list[dict[str, list[str]]] = []

    def snapshot_for_query(self, query: dict[str, list[str]]) -> FakeSnapshot:
        self.queries.append(query)
        return self.snapshot


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


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "judge-total-bases",
        "propKey": "judge-total-bases",
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
    row.update(overrides)
    return row


def _service(snapshot: FakeSnapshot, model_card_service: Any | None = None) -> PropDetailService:
    return PropDetailService(
        read_service=FakeReadService(snapshot),
        model_card_service=model_card_service or FakeModelCardService(),
        picks_service=FakePicksService(),
    )


def test_prop_detail_builds_price_model_context_and_tracking_payload() -> None:
    snapshot = FakeSnapshot([_row()])
    payload = _service(snapshot).payload({"propKey": ["judge-total-bases"], "market": ["batter_total_bases"]})

    assert payload["status"] == "ok"
    assert payload["source"]["lookupMode"] == "prop_key"
    assert payload["source"]["lookupMode"] != "legacy_edge_board_scan"
    assert snapshot.row_for_prop_key_calls == ["judge-total-bases"]
    detail = payload["detail"]
    assert detail["overview"]["player"] == "Aaron Judge"
    assert detail["priceComparison"]["bestAvailable"]["americanOdds"] == "+115"
    assert detail["priceComparison"]["noVigFairEstimate"]["fairAmericanOdds"] == "-120"
    assert detail["modelExplanation"]["trainingRows"] == 190
    assert detail["riskContext"]["exposure"]["activePickCount"] == 1
    assert detail["tracking"]["separateFromModelBacktests"] is True
    assert detail["tracking"]["payload"]["source"] == "prop_detail"
    assert detail["tracking"]["payload"]["stakeUnits"] == 0


def test_prop_detail_can_fallback_from_query_without_snapshot_row() -> None:
    payload = _service(FakeSnapshot([])).payload({"player": ["Missing Player"], "market": ["batter_hits"], "team": ["NYY"], "opponent": ["BAL"]})

    detail = payload["detail"]
    assert payload["source"]["lookupMode"] == "not_found"
    assert payload["source"]["lookupMode"] != "legacy_edge_board_scan"
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
        raise AssertionError("PropDetailService should reuse the embedded snapshot-row modelCard")


def test_prop_detail_reuses_embedded_model_card_from_snapshot_row() -> None:
    embedded = {
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
    payload = _service(FakeSnapshot([_row(modelCard=embedded)]), ExplodingModelCardService()).payload(
        {"propKey": ["judge-total-bases"], "market": ["batter_total_bases"]}
    )

    assert payload["source"]["boardCache"]["hit"] is True
    assert payload["source"]["modelCardSource"] == "playerboard_snapshot_row"
    assert payload["detail"]["modelExplanation"]["backtest"]["roiPercent"] == -39.18


def test_prop_detail_has_no_edge_board_dependency() -> None:
    service = _service(FakeSnapshot([_row()]))

    assert not hasattr(service, "edge_board_service")
    assert "edge_board_service" not in PropDetailService.__init__.__annotations__
