from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.player_prop_prediction_repository import (
    PlayerPropPredictionRepository,
    prediction_key_for_board_row,
)


class FakePlayerboardService:
    def __init__(self, rows: list[dict[str, Any]] | None = None, *, date_label: str = "2026-05-07") -> None:
        self.rows = rows
        self.date_label = date_label

    def board_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        rows = self.rows or [
            {
                "date": self.date_label,
                "player": "Aaron Judge",
                "team": "NYY",
                "opponent": "BAL",
                "market": "batter_total_bases",
                "marketDisplay": "Batter Total Bases",
                "line": "1.5",
                "side": "Over",
                "book": "DraftKings",
                "bookKey": "draftkings",
                "americanOdds": "-110",
                "finalProbabilityPercent": "57.5",
                "finalEdgePercent": "4.2",
                "confidence": "Medium",
            }
        ]
        return {
            "season": 2026,
            "date": self.date_label,
            "top": rows,
            "cardsBuilt": len(rows),
            "propsLoaded": len(rows),
            "latestFullyGradedDate": "2026-05-06",
            "dataConfidence": "Partial",
            "trust": {"banner": "Research Mode", "mode": "research_mode"},
            "freshness": {"status": "fresh", "ageSeconds": 120, "snapshotBuiltAt": "2026-05-07T15:00:00Z"},
            "productState": {"state": "research_mode"},
        }


class FakeModelCardService:
    def __init__(self, *, readiness_label: str = "Research only") -> None:
        self.readiness_label = readiness_label

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        return {
            "markets": [self.card_for_market("batter_total_bases")],
            "status": "ok",
        }

    def card_for_market(self, market: str) -> dict[str, Any]:
        return {
            "market": market,
            "readinessLabel": self.readiness_label,
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


def test_edge_board_prediction_match_populates_model_probability_and_edge(tmp_path: Path) -> None:
    date_label = "2026-06-29"
    row = _board_row(date_label=date_label)
    settings = _settings(tmp_path)
    _write_predictions(settings, date_label, [_prediction_for(row, date_label=date_label, warnings="experimental_warning")])

    payload = _prediction_service_payload(settings, [row], date_label=date_label)

    matched = payload["rows"][0]
    assert matched["modelProbabilityPercent"] == "61.25"
    assert matched["impliedProbabilityPercent"] == "52.38"
    assert matched["edgePercent"] == "8.87"
    assert matched["fairOdds"] == "-158"
    assert matched["expectedValue"] == "0.1691"
    assert matched["readinessLabel"] == "Experimental"
    assert matched["modelReadiness"] == "Experimental"
    assert matched["action"] == "Research"
    assert matched["stakeUnits"] == 0
    assert matched["predictionMatched"] is True
    assert matched["predictionWarnings"] == ["experimental_warning"]
    assert matched["trust"]["modelEdge"]["modelProbabilityPercent"] == 61.25
    assert payload["meta"]["predictionsLoaded"] == 1
    assert payload["meta"]["predictionsFileRows"] == 1
    assert payload["meta"]["predictionsMatched"] == 1
    assert payload["meta"]["predictionsMissing"] == 0
    assert payload["meta"]["predictionsAmbiguous"] == 0
    assert payload["meta"]["predictionsByMarket"] == {"batter_hits": 1}
    assert payload["summary"]["modeledMarkets"] == 1
    assert payload["summary"]["modeledRows"] == 1


def test_edge_board_unmatched_row_stays_no_model_no_bet(tmp_path: Path) -> None:
    date_label = "2026-06-29"
    row = _board_row(date_label=date_label)
    other_row = dict(row, player="Juan Soto")
    settings = _settings(tmp_path)
    _write_predictions(settings, date_label, [_prediction_for(other_row, date_label=date_label)])

    payload = _prediction_service_payload(settings, [row], date_label=date_label)

    unmatched = payload["rows"][0]
    assert unmatched["predictionMatched"] is not True
    assert unmatched["predictionKey"] == ""
    assert unmatched["predictionSource"] == ""
    assert unmatched["predictionWarnings"] == []
    assert unmatched["action"] == "No bet"
    assert unmatched["stakeUnits"] == 0
    assert unmatched["modelProbabilityPercent"] == ""
    assert unmatched["edgePercent"] == ""
    assert unmatched["readinessLabel"] == "No model"
    assert unmatched["decisionLabel"] == "No bet"
    assert payload["summary"]["modeledMarkets"] == 0
    assert payload["summary"]["modeledRows"] == 0
    assert payload["meta"]["predictionsLoaded"] == 1
    assert payload["meta"]["predictionsMatched"] == 0
    assert payload["meta"]["predictionsMissing"] == 1


def test_edge_board_ambiguous_prediction_match_does_not_join(tmp_path: Path) -> None:
    date_label = "2026-06-29"
    row = _board_row(date_label=date_label)
    settings = _settings(tmp_path)
    prediction = _prediction_for(row, date_label=date_label)
    _write_predictions(settings, date_label, [prediction, dict(prediction, edgePercent="12.5")])

    payload = _prediction_service_payload(settings, [row], date_label=date_label)

    ambiguous = payload["rows"][0]
    assert ambiguous["predictionMatched"] is not True
    assert ambiguous["modelProbabilityPercent"] == ""
    assert ambiguous["edgePercent"] == ""
    assert payload["meta"]["predictionsMatched"] == 0
    assert payload["meta"]["predictionsAmbiguous"] == 1


def test_edge_board_missing_prediction_file_does_not_break_board(tmp_path: Path) -> None:
    date_label = "2026-06-29"
    row = _board_row(date_label=date_label)
    settings = _settings(tmp_path)

    payload = _prediction_service_payload(settings, [row], date_label=date_label)

    assert payload["status"] == "ok"
    assert payload["rowCount"] == 1
    assert payload["rows"][0]["decisionLabel"] == "No bet"
    assert payload["meta"]["predictionsLoaded"] == 0
    assert payload["meta"]["predictionsMatched"] == 0
    assert payload["meta"]["predictionsMissing"] == 1


def test_edge_board_stale_prediction_rows_do_not_join(tmp_path: Path) -> None:
    date_label = "2026-06-29"
    stale_date = "2026-06-28"
    row = _board_row(date_label=date_label)
    settings = _settings(tmp_path)
    _write_predictions(settings, date_label, [_prediction_for(row, date_label=stale_date)])

    payload = _prediction_service_payload(settings, [row], date_label=date_label)

    unmatched = payload["rows"][0]
    assert unmatched["predictionMatched"] is not True
    assert payload["meta"]["predictionsLoaded"] == 0
    assert payload["meta"]["predictionsFileRows"] == 1
    assert payload["meta"]["predictionsRejectedDateMismatch"] == 1
    assert payload["meta"]["predictionsMatched"] == 0
    assert payload["meta"]["predictionsMissing"] == 1


def test_edge_board_request_date_mismatch_skips_prediction_join(tmp_path: Path) -> None:
    requested_date = "2026-06-29"
    board_date = "2026-06-28"
    row = _board_row(date_label=board_date)
    settings = _settings(tmp_path)
    _write_predictions(settings, board_date, [_prediction_for(row, date_label=board_date)])

    payload = EdgeBoardService(
        playerboard_service=FakePlayerboardService([row], date_label=board_date),
        model_card_service=FakeModelCardService(readiness_label="No model"),
        player_prop_prediction_repository=PlayerPropPredictionRepository(settings=settings),
        settings=settings,
    ).payload({"season": ["2026"], "date": [requested_date]})

    unmatched = payload["rows"][0]
    assert unmatched["predictionMatched"] is not True
    assert payload["meta"]["predictionDate"] == requested_date
    assert payload["meta"]["predictionBoardDate"] == board_date
    assert payload["meta"]["predictionsLoaded"] == 0
    assert payload["meta"]["predictionsMatched"] == 0
    assert payload["meta"]["predictionsMissing"] == 1


def test_edge_board_prediction_action_remains_research_and_stake_zero(tmp_path: Path) -> None:
    date_label = "2026-06-29"
    row = _board_row(date_label=date_label)
    settings = _settings(tmp_path)
    _write_predictions(
        settings,
        date_label,
        [_prediction_for(row, date_label=date_label, modelProbabilityPercent="92.1", edgePercent="44.2")],
    )

    payload = _prediction_service_payload(settings, [row], date_label=date_label)

    matched = payload["rows"][0]
    assert matched["action"] == "Research"
    assert matched["stakeUnits"] == 0
    assert matched["trust"]["actionability"]["suggestedStake"] == "Research only"
    assert matched["trust"]["actionability"]["stakeUnits"] == 0


def test_edge_board_snapshot_rows_keep_prediction_contract_and_normalize_side() -> None:
    row = EdgeBoardService._snapshot_contract_row(
        {
            "predictionMatched": True,
            "rawLabel": "Aaron Judge Over 0.5 Hits",
            "readinessLabel": "No model",
            "action": "Bet",
            "stakeUnits": 1,
            "trust": {"actionability": {"label": "Bet", "stakeUnits": 1}},
        }
    )

    assert row["side"] == "Over"
    assert row["predictionMatched"] is True
    assert row["readinessLabel"] == "Experimental"
    assert row["action"] == "Research"
    assert row["actionLabel"] == "Research"
    assert row["stakeUnits"] == 0
    assert row["trust"]["actionability"]["label"] == "Research"
    assert row["trust"]["actionability"]["stakeUnits"] == 0


def _prediction_service_payload(settings: Settings, rows: list[dict[str, Any]], *, date_label: str) -> dict[str, Any]:
    return EdgeBoardService(
        playerboard_service=FakePlayerboardService(rows, date_label=date_label),
        model_card_service=FakeModelCardService(readiness_label="No model"),
        player_prop_prediction_repository=PlayerPropPredictionRepository(settings=settings),
        settings=settings,
    ).payload({"season": ["2026"], "date": [date_label]})


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "data" / "models",
        model_registry_path=tmp_path / "data" / "models" / "model_registry.json",
        current_season=2026,
    )


def _board_row(*, date_label: str) -> dict[str, Any]:
    return {
        "date": date_label,
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_hits",
        "marketDisplay": "Batter Hits",
        "line": "0.5",
        "side": "Over",
        "book": "DraftKings",
        "bookKey": "draftkings",
        "americanOdds": "-110",
    }


def _prediction_for(row: dict[str, Any], *, date_label: str, **overrides: Any) -> dict[str, Any]:
    prediction = {
        "date": date_label,
        "season": "2026",
        "market": row["market"],
        "player": row["player"],
        "team": row["team"],
        "opponent": row["opponent"],
        "book": row["book"],
        "bookKey": row["bookKey"],
        "line": row["line"],
        "side": row["side"],
        "americanOdds": row["americanOdds"],
        "modelProbabilityPercent": "61.25",
        "impliedProbabilityPercent": "52.38",
        "edgePercent": "8.87",
        "fairOdds": "-158",
        "expectedValue": "0.1691",
        "readinessLabel": "Experimental",
        "action": "Research",
        "stakeUnits": "0",
        "predictionKey": prediction_key_for_board_row(row, date_label=date_label),
        "joinKeyStrength": "strong",
        "warnings": "",
    }
    prediction.update(overrides)
    return prediction


def _write_predictions(settings: Settings, date_label: str, rows: list[dict[str, Any]]) -> None:
    path = settings.data_dir / "predictions" / f"prop_predictions_{date_label}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "date",
        "season",
        "market",
        "player",
        "team",
        "opponent",
        "book",
        "bookKey",
        "line",
        "side",
        "americanOdds",
        "modelProbabilityPercent",
        "impliedProbabilityPercent",
        "edgePercent",
        "fairOdds",
        "expectedValue",
        "readinessLabel",
        "action",
        "stakeUnits",
        "predictionKey",
        "joinKeyStrength",
        "warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
