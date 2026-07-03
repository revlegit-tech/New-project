from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.player_prop_prediction_repository import PlayerPropPredictionRepository


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


def test_rows_without_predictions_receive_safe_default_trust_envelope(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    row = PlayerPropPredictionRepository(settings=settings).join_predictions(
        [base_row()],
        date_label="2026-06-29",
    ).rows[0]

    assert row["predictionMatched"] is False
    assert row["trustTier"]
    assert row["calibrationStatus"] == "not_applicable"
    assert row["probabilityGuardrailStatus"] in {"blocked", "not_applicable"}
    assert row["contextReadinessStatus"]
    assert row["modelProbabilitySource"] == "none"
    assert row["modelProbabilityPercent"] == ""
    assert row["edgePercent"] == ""
    assert row["action"] == "Research"
    assert row["readinessLabel"] == "Experimental"
    assert row["stakeUnits"] == 0
    assert row["betActionAllowed"] is False


def test_unsupported_market_row_is_explainable_without_fake_model_output(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    row = PlayerPropPredictionRepository(settings=settings).join_predictions(
        [base_row(market="batter_stolen_bases")],
        date_label="2026-06-29",
    ).rows[0]

    assert row["unscoredReason"] == "unsupported_market"
    assert row["trustTier"] == "unsupported"
    assert "unsupported_market" in row["trustReasons"]
    assert row["unsupportedMarketReason"] == "unsupported_market:batter_stolen_bases"
    assert row["modelProbabilityPercent"] == ""
    assert row["edgePercent"] == ""
    assert row["betActionAllowed"] is False


def test_missing_odds_row_gets_blocked_guardrail_without_fake_edge(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    row = PlayerPropPredictionRepository(settings=settings).join_predictions(
        [base_row(americanOdds="", bestAmericanOdds="", selectedBookAmericanOdds="")],
        date_label="2026-06-29",
    ).rows[0]

    assert row["unscoredReason"] == "missing_odds"
    assert row["probabilityGuardrailStatus"] == "blocked"
    assert "model_probability_not_emitted" in row["probabilityGuardrailReasons"]
    assert "edge_not_emitted" in row["probabilityGuardrailReasons"]
    assert row["modelProbabilityPercent"] == ""
    assert row["edgePercent"] == ""


def test_invalid_and_inferred_attribution_rows_remain_low_or_blocked_trust(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    rows = PlayerPropPredictionRepository(settings=settings).join_predictions(
        [
            base_row(player="Over 1.5", attributionStatus="invalid_player_label"),
            base_row(player="Juan Soto", attributionStatus="inferred_low_confidence", identityConfidence="weak"),
        ],
        date_label="2026-06-29",
    ).rows

    invalid = rows[0]
    inferred = rows[1]
    assert invalid["unscoredReason"] == "invalid_attribution"
    assert invalid["trustTier"] == "blocked"
    assert invalid["attributionBlockReason"] == "invalid_player_label"
    assert inferred["trustTier"] == "low"
    assert inferred["contextReadinessStatus"] == "limited"
    assert inferred["unscoredReason"] == ""
    assert inferred["unscoredReasonDetail"] == ""
    assert inferred["missingPredictionReason"] == ""


def test_data_status_reports_zero_blank_trust_fields_after_fallback(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            base_row(),
            base_row(player="Runner Example", market="batter_stolen_bases"),
            base_row(player="No Odds", americanOdds=""),
        ],
    )

    payload = DataStatusService(
        settings=settings,
        now_provider=lambda: datetime(2026, 6, 29, 12, tzinfo=timezone.utc),
    ).payload({"season": ["2026"]})

    health = payload["playerboard_build_health"]
    assert health["trustCoverage"]["totalBoardRows"] == 3
    assert health["trustCoverage"]["totalRowsMissingTrustTier"] == 0
    assert health["trustCoverage"]["totalRowsMissingGuardrailStatus"] == 0
    assert health["trustCoverage"]["totalRowsMissingCalibrationStatus"] == 0
    assert health["trustCoverage"]["totalRowsMissingContextReadinessStatus"] == 0
    assert health["blankTrustFieldCounts"] == {
        "totalRowsMissingTrustTier": 0,
        "totalRowsMissingGuardrailStatus": 0,
        "totalRowsMissingCalibrationStatus": 0,
        "totalRowsMissingContextReadinessStatus": 0,
    }
    assert health["unscoredReasonCounts"]["unsupported_market"] == 1
    assert health["unscoredReasonCounts"]["missing_odds"] == 1
    assert health["sampleBlankTrustRows"] == []
    assert health["sampleUnscoredRows"]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
