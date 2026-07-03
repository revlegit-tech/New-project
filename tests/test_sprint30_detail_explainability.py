from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.contracts.playerboard_schema import PLAYERBOARD_FIELDS
from mlb_app.repositories.playerboard_repository import PlayerboardRepository
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.player_prop_explainability_service import compose_player_prop_explainability
from mlb_app.services.player_prop_prediction_repository import prediction_key_for_board_row


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "data" / "models",
        model_registry_path=tmp_path / "data" / "models" / "model_registry.json",
        current_season=2026,
        db_enabled=False,
    )


def base_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "snapshotAt": "2026-06-29T15:00:00+00:00",
        "season": "2026",
        "date": "2026-06-29",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_hits",
        "marketDisplay": "Batter Hits",
        "baseMarket": "batter_hits",
        "side": "Over",
        "rawLabel": "Over",
        "line": "0.5",
        "book": "DraftKings",
        "bookKey": "draftkings",
        "americanOdds": "-110",
        "attributionStatus": "verified",
    }
    row.update(overrides)
    return row


def standard_scored_row(**overrides: Any) -> dict[str, Any]:
    row = base_row(
        predictionMatched=True,
        modelProbabilityPercent="61.25",
        edgePercent="8.15",
        impliedProbabilityPercent="53.10",
        modelProbabilitySource="calibrated_model",
        modelFamily="xgboost",
        modelVersion="2026.06.29",
        calibrationStatus="applied",
        calibrationBucket="batter_hits|over|line:0-0.5",
        calibrationSampleSize=250,
        probabilityGuardrailStatus="ok",
        trustTier="standard",
        trustScore=82,
        trustReasons=["verified_attribution", "calibrated_model"],
        contextReadinessStatus="ready",
        readyFeatureGroups=["weather", "statcast"],
        action="Research",
        readinessLabel="Experimental",
        stakeUnits=0,
        betActionAllowed=False,
        researchOnlyReason="research_lock",
    )
    row.update(overrides)
    return row


def test_standard_row_explainability_includes_model_calibration_and_context_summary() -> None:
    explainability = compose_player_prop_explainability(standard_scored_row())

    assert explainability["trustTier"] == "standard"
    assert explainability["trustScore"] == 82
    assert explainability["model"]["hasModelProbability"] is True
    assert explainability["model"]["modelProbabilityPercent"] == "61.25"
    assert explainability["model"]["edgePercent"] == "8.15"
    assert explainability["calibration"]["calibrationStatus"] == "applied"
    assert explainability["context"]["contextReadinessStatus"] == "ready"
    assert explainability["guardrails"]["probabilityGuardrailStatus"] == "ok"
    assert "Model probability and edge are existing scored outputs" in explainability["model"]["explanation"]


def test_standard_row_has_no_unscored_reason_in_explainability() -> None:
    explainability = compose_player_prop_explainability(
        standard_scored_row(
            unscoredReason="missing_prediction",
            unscoredReasonDetail="No matching model prediction row was found for this board row.",
            missingPredictionReason="prediction_join_no_match",
            probabilityGuardrailReasons=["missing_prediction", "prediction_join_no_match"],
        )
    )

    assert explainability["guardrails"]["unscoredReason"] == ""
    assert explainability["guardrails"]["unscoredReasonDetail"] == ""
    assert explainability["guardrails"]["missingPredictionReason"] == ""
    assert "missing_prediction" not in str(explainability)
    assert "prediction_join_no_match" not in explainability["blocks"]


def test_low_row_has_no_unscored_reason_in_explainability() -> None:
    explainability = compose_player_prop_explainability(
        standard_scored_row(
            trustTier="low",
            trustScore=35,
            unscoredReason="missing_prediction",
            missingPredictionReason="prediction_join_no_match",
        )
    )

    assert explainability["trustTier"] == "low"
    assert explainability["guardrails"]["unscoredReason"] == ""
    assert explainability["guardrails"]["missingPredictionReason"] == ""


def test_limited_row_has_no_unscored_reason_in_explainability() -> None:
    explainability = compose_player_prop_explainability(
        standard_scored_row(
            trustTier="limited",
            contextReadinessStatus="limited",
            unscoredReason="missing_prediction",
            scoringSkipReason="ambiguous_prediction_match",
            missingPredictionReason="prediction_join_no_match",
        )
    )

    assert explainability["trustTier"] == "limited"
    assert explainability["guardrails"]["unscoredReason"] == ""
    assert explainability["guardrails"]["scoringSkipReason"] == ""
    assert explainability["guardrails"]["missingPredictionReason"] == ""


def test_low_trust_uncalibrated_row_explains_calibration_not_available() -> None:
    explainability = compose_player_prop_explainability(
        standard_scored_row(
            trustTier="low",
            trustScore=35,
            calibrationStatus="not_available",
            calibrationWarning="minimum_sample_size_not_met",
            contextReadinessStatus="limited",
            fallbackFeatureGroups=["weather"],
        )
    )

    assert explainability["trustTier"] == "low"
    assert "calibration is not_available" in explainability["summary"]
    assert explainability["calibration"]["calibrationStatus"] == "not_available"
    assert "not available" in explainability["calibration"]["explanation"]
    assert "Review calibration availability." in explainability["nextChecks"]


def test_blocked_invalid_player_label_row_explains_attribution_block() -> None:
    explainability = compose_player_prop_explainability(
        base_row(
            player="Over 1.5",
            attributionStatus="invalid_player_label",
            attributionBlockReason="invalid_player_label",
            invalidPlayerLabel=True,
            trustTier="blocked",
            trustScore=0,
            probabilityGuardrailStatus="blocked",
            probabilityGuardrailReasons=["invalid_player_label"],
            unscoredReason="invalid_attribution",
            modelProbabilityPercent="",
            edgePercent="",
            action="Research",
            readinessLabel="Experimental",
            stakeUnits=0,
            betActionAllowed=False,
        )
    )

    assert explainability["attribution"]["invalidPlayerLabel"] is True
    assert explainability["attribution"]["attributionBlockReason"] == "invalid_player_label"
    assert "invalid" in explainability["attribution"]["explanation"]
    assert "invalid_player_label" in explainability["blocks"]
    assert explainability["researchOnly"]["betActionAllowed"] is False
    assert explainability["guardrails"]["unscoredReason"] == "invalid_attribution"


def test_unscored_unsupported_row_explains_withheld_model_without_fake_output() -> None:
    explainability = compose_player_prop_explainability(
        base_row(
            market="batter_stolen_bases",
            trustTier="unsupported",
            trustScore=0,
            modelProbabilitySource="none",
            probabilityGuardrailStatus="blocked",
            unsupportedMarketReason="unsupported_market:batter_stolen_bases",
            unscoredReason="unsupported_market",
            unscoredReasonDetail="unsupported_market:batter_stolen_bases",
            missingPredictionReason="",
            modelProbabilityPercent="",
            edgePercent="",
            action="Research",
            readinessLabel="Experimental",
            stakeUnits=0,
            betActionAllowed=False,
        )
    )

    assert explainability["model"]["hasModelProbability"] is False
    assert "modelProbabilityPercent" not in explainability["model"]
    assert "edgePercent" not in explainability["model"]
    assert explainability["guardrails"]["unsupportedMarketReason"] == "unsupported_market:batter_stolen_bases"
    assert "unsupported_market" in explainability["model"]["explanation"]


def test_null_probability_and_edge_are_not_invented_in_explainability() -> None:
    explainability = compose_player_prop_explainability(
        base_row(
            trustTier="unscored",
            modelProbabilityPercent=None,
            edgePercent=None,
            probabilityGuardrailStatus="blocked",
            unscoredReason="missing_prediction",
            missingPredictionReason="prediction_join_no_match",
        )
    )

    assert explainability["model"]["hasModelProbability"] is False
    assert "modelProbabilityPercent" not in explainability["model"]
    assert "edgePercent" not in explainability["model"]
    assert explainability["guardrails"]["unscoredReason"] == "missing_prediction"
    assert explainability["guardrails"]["missingPredictionReason"] == "prediction_join_no_match"


def test_research_lock_is_included_in_explainability() -> None:
    explainability = compose_player_prop_explainability(standard_scored_row())

    assert explainability["researchOnly"] == {
        "action": "Research",
        "readinessLabel": "Experimental",
        "stakeUnits": 0,
        "betActionAllowed": False,
        "researchOnlyReason": "research_lock",
        "explanation": "This row is research-only; bet actions and staking remain disabled.",
    }


def test_every_playerboard_api_row_receives_explainability(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repository = PlayerboardRepository(settings=settings)
    _write_playerboard(
        repository.path_for_season(2026),
        [
            base_row(),
            base_row(player="Juan Soto", market="batter_stolen_bases"),
        ],
    )
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/playerboard?season=2026&date=2026-06-29&limit=10")

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 2
    assert all(isinstance(row.get("explainability"), dict) for row in rows)
    assert all(row["explainability"]["researchOnly"]["action"] == "Research" for row in rows)
    assert all(
        row["explainability"]["guardrails"]["unscoredReason"]
        for row in rows
        if row.get("trustTier") in {"unscored", "blocked", "unsupported"}
    )


def test_playerboard_api_scored_rows_do_not_leak_unscored_reasons(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repository = PlayerboardRepository(settings=settings)
    row = base_row(player="Miguel Vargas", market="batter_hits")
    _write_playerboard(repository.path_for_season(2026), [row])
    _write_predictions(settings, "2026-06-29", [_prediction_for(row, date_label="2026-06-29", trustTier="standard")])
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/playerboard?season=2026&date=2026-06-29&limit=10")

    assert response.status_code == 200
    rows = response.json()["rows"]
    leaking = [
        item
        for item in rows
        if item.get("trustTier") in {"standard", "low", "limited"} and str(item.get("unscoredReason") or "").strip()
    ]
    assert leaking == []
    assert rows[0]["trustTier"] == "standard"
    assert rows[0]["unscoredReason"] in {None, ""}
    assert rows[0]["missingPredictionReason"] in {None, ""}
    assert rows[0]["explainability"]["guardrails"]["unscoredReason"] == ""
    assert "missing_prediction" not in str(rows[0]["explainability"])
    assert "prediction_join_no_match" not in rows[0]["explainability"]["blocks"]


def test_data_status_explainability_coverage_reports_zero_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            base_row(player="Missing Prediction"),
            base_row(player="Unsupported Market", market="batter_stolen_bases"),
            base_row(player="Over 1.5", attributionStatus="invalid_player_label"),
        ],
    )

    health = DataStatusService(
        settings=settings,
        now_provider=lambda: datetime(2026, 6, 29, 16, tzinfo=timezone.utc),
    ).payload({"season": ["2026"]})["playerboard_build_health"]

    assert health["explainabilityCoverage"]["rowsMissingExplainability"] == 0
    assert health["rowsMissingExplainability"] == 0
    assert health["rowsWithExplainability"] == 3
    assert health["sampleMissingExplainabilityRows"] == []
    assert "unscored" in health["sampleExplainabilityRowsByTier"]
    assert "unsupported" in health["sampleExplainabilityRowsByTier"]
    assert "blocked" in health["sampleExplainabilityRowsByTier"]


def _write_playerboard(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAYERBOARD_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PLAYERBOARD_FIELDS})


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
        "rawModelProbability": "0.59",
        "calibratedProbability": "0.6125",
        "calibrationApplied": "true",
        "calibrationMethod": "isotonic",
        "calibrationStatus": "applied",
        "modelProbabilityPercent": "61.25",
        "impliedProbabilityPercent": "52.38",
        "edgePercent": "8.87",
        "fairOdds": "-158",
        "expectedValue": "0.1691",
        "modelProbabilitySource": "calibrated_model",
        "trustTier": "standard",
        "trustScore": "82",
        "trustReasons": "verified_attribution|calibrated_model",
        "contextReadinessStatus": "ready",
        "probabilityGuardrailStatus": "ok",
        "readinessLabel": "Experimental",
        "action": "Research",
        "stakeUnits": "0",
        "predictionKey": prediction_key_for_board_row(row, date_label=date_label),
        "joinKeyStrength": "strong",
        "productionEligible": "false",
        "betActionAllowed": "false",
    }
    prediction.update(overrides)
    return prediction


def _write_predictions(settings: Settings, date_label: str, rows: list[dict[str, Any]]) -> None:
    path = settings.data_dir / "predictions" / f"prop_predictions_{date_label}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
