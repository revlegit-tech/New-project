from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.player_prop_prediction_repository import PlayerPropPredictionRepository, prediction_key_for_board_row


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
        "date": "2026-06-29",
        "snapshotAt": "2026-06-29T15:00:00+00:00",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_hits",
        "side": "Over",
        "line": "0.5",
        "book": "DraftKings",
        "bookKey": "draftkings",
        "americanOdds": "-110",
        "attributionStatus": "verified",
    }
    row.update(overrides)
    return row


def test_data_status_active_trust_coverage_uses_latest_active_slate_scope(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            base_row(player="Active Missing Prediction"),
            base_row(player="Active Unsupported", market="batter_stolen_bases"),
            base_row(date="2026-06-28", snapshotAt="2026-06-28T15:00:00+00:00", player="Old Row"),
        ],
    )

    health = DataStatusService(
        settings=settings,
        now_provider=lambda: datetime(2026, 6, 29, 16, tzinfo=timezone.utc),
    ).payload({"season": ["2026"]})["playerboard_build_health"]

    assert health["trustCoverageScope"] == "active_slate"
    assert health["activeDate"] == "2026-06-29"
    assert health["activeSlateRows"] == 2
    assert health["seasonRows"] == 3
    assert health["statusRowsEvaluated"] == 2
    assert health["rowsExcludedByDateScope"] == 1
    assert health["trustCoverage"]["totalBoardRows"] == 2
    assert health["seasonTrustCoverage"]["totalBoardRows"] == 3
    assert health["sourceOfTrustCoverage"] == "csv_season_artifact"


def test_season_rows_do_not_pollute_active_unscored_reason_counts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            base_row(player="Active Missing Prediction"),
            base_row(date="2026-06-28", snapshotAt="2026-06-28T15:00:00+00:00", player="Old Unsupported", market="batter_stolen_bases"),
        ],
    )

    health = DataStatusService(
        settings=settings,
        now_provider=lambda: datetime(2026, 6, 29, 16, tzinfo=timezone.utc),
    ).payload({"season": ["2026"]})["playerboard_build_health"]

    assert health["unscoredReasonCounts"] == {"missing_prediction": 1}
    assert health["unscoredReasonCountsByScope"]["active_slate"] == {"missing_prediction": 1}
    assert health["unscoredReasonCountsByScope"]["season_artifact"]["season_row_not_active_slate"] == 1
    assert health["sampleOutsideActiveSlateRows"]


def test_unscored_reason_counts_classify_supported_cases(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            base_row(player="Missing Prediction"),
            base_row(player="Unsupported Market", market="batter_stolen_bases"),
            base_row(player="Over 1.5", attributionStatus="invalid_player_label"),
            base_row(player="No Odds", americanOdds="", bestAmericanOdds="", selectedBookAmericanOdds=""),
        ],
    )

    health = DataStatusService(
        settings=settings,
        now_provider=lambda: datetime(2026, 6, 29, 16, tzinfo=timezone.utc),
    ).payload({"season": ["2026"]})["playerboard_build_health"]

    assert health["unscoredReasonCounts"]["missing_prediction"] == 1
    assert health["unscoredReasonCounts"]["unsupported_market"] == 1
    assert health["unscoredReasonCounts"]["invalid_attribution"] == 1
    assert health["unscoredReasonCounts"]["missing_odds"] == 1
    assert "unknown_unscored" not in health["unscoredReasonCounts"]
    assert health["unknownUnscoredDiagnostics"]["unknownUnscoredRows"] == 0
    assert health["sampleUnscoredRowsByReason"]["unsupported_market"][0]["unsupportedMarketReason"]
    assert health["sampleUnscoredRowsByReason"]["missing_prediction"][0]["missingPredictionReason"] == "prediction_join_no_match"


def test_active_blank_trust_fields_remain_zero(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [base_row(), base_row(player="Unsupported Market", market="batter_stolen_bases")],
    )

    health = DataStatusService(
        settings=settings,
        now_provider=lambda: datetime(2026, 6, 29, 16, tzinfo=timezone.utc),
    ).payload({"season": ["2026"]})["playerboard_build_health"]

    assert health["blankTrustFieldCounts"] == {
        "totalRowsMissingTrustTier": 0,
        "totalRowsMissingGuardrailStatus": 0,
        "totalRowsMissingCalibrationStatus": 0,
        "totalRowsMissingContextReadinessStatus": 0,
    }
    assert health["sampleBlankTrustRows"] == []


def test_unscored_rows_do_not_receive_fake_model_outputs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    row = PlayerPropPredictionRepository(settings=settings).join_predictions(
        [base_row()],
        date_label="2026-06-29",
    ).rows[0]

    assert row["unscoredReason"] == "missing_prediction"
    assert row["unscoredReasonDetail"]
    assert row["missingPredictionReason"] == "prediction_join_no_match"
    assert row["modelProbabilityPercent"] == ""
    assert row["rawModelProbability"] == ""
    assert row["calibratedProbability"] == ""
    assert row["edgePercent"] == ""
    assert row["action"] == "Research"
    assert row["readinessLabel"] == "Experimental"
    assert row["stakeUnits"] == 0
    assert row["betActionAllowed"] is False


def test_matched_standard_row_clears_prejoin_unscored_reasons(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    board_row = base_row(unscoredReason="missing_prediction", missingPredictionReason="prediction_join_no_match")
    write_csv(settings.data_dir / "predictions" / "prop_predictions_2026-06-29.csv", [_prediction_for(board_row, trustTier="standard")])

    row = PlayerPropPredictionRepository(settings=settings).join_predictions([board_row], date_label="2026-06-29").rows[0]

    assert row["trustTier"] == "standard"
    assert row["unscoredReason"] == ""
    assert row["unscoredReasonDetail"] == ""
    assert row["missingPredictionReason"] == ""
    assert row["scoringSkipReason"] == ""


def test_matched_low_row_clears_prejoin_unscored_reasons(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    board_row = base_row(unscoredReason="missing_prediction", missingPredictionReason="prediction_join_no_match")
    write_csv(settings.data_dir / "predictions" / "prop_predictions_2026-06-29.csv", [_prediction_for(board_row, trustTier="low")])

    row = PlayerPropPredictionRepository(settings=settings).join_predictions([board_row], date_label="2026-06-29").rows[0]

    assert row["trustTier"] == "low"
    assert row["unscoredReason"] == ""
    assert row["missingPredictionReason"] == ""


def test_matched_limited_row_clears_prejoin_unscored_reasons(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    board_row = base_row(unscoredReason="missing_prediction", missingPredictionReason="prediction_join_no_match")
    write_csv(settings.data_dir / "predictions" / "prop_predictions_2026-06-29.csv", [_prediction_for(board_row, trustTier="limited")])

    row = PlayerPropPredictionRepository(settings=settings).join_predictions([board_row], date_label="2026-06-29").rows[0]

    assert row["trustTier"] == "limited"
    assert row["unscoredReason"] == ""
    assert row["missingPredictionReason"] == ""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prediction_for(row: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    date_label = str(row.get("date") or "2026-06-29")
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
        "calibrationStatus": "applied",
        "modelProbabilityPercent": "61.25",
        "impliedProbabilityPercent": "52.38",
        "edgePercent": "8.87",
        "modelProbabilitySource": "calibrated_model",
        "trustTier": "standard",
        "trustScore": "82",
        "trustReasons": "verified_attribution|missing_prediction|prediction_join_no_match",
        "contextReadinessStatus": "ready",
        "probabilityGuardrailStatus": "ok",
        "probabilityGuardrailReasons": "missing_prediction|prediction_join_no_match",
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
