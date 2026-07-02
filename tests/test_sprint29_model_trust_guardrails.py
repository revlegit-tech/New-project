from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

from mlb_app.config import Settings
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.player_prop_model_scoring_service import PlayerPropModelScoringService


class TinyProbabilityModel:
    def __init__(self, probability: float = 0.62) -> None:
        self.probability = probability

    def predict_proba(self, matrix: Any) -> list[list[float]]:
        return [[1.0 - self.probability, self.probability] for _ in range(len(matrix))]


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        current_season=2026,
        db_enabled=False,
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_model(settings: Settings, market: str, probability: float = 0.62) -> Path:
    path = settings.model_dir / f"prop_model_{market}.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(TinyProbabilityModel(probability), path)
    return path


def write_calibration(settings: Settings, market: str, *, intercept: float = 0.05) -> Path:
    path = settings.model_dir / "calibration" / f"player_prop_calibration_{market}.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "schemaVersion": "player-prop-calibration.v1",
            "status": "ready",
            "market": market,
            "method": "isotonic",
            "generatedAt": "2026-06-30T00:00:00+00:00",
            "sampleSize": 250,
            "minSampleSize": 200,
            "brierScoreBefore": 0.22,
            "brierScoreAfter": 0.20,
            "logLossBefore": 0.68,
            "logLossAfter": 0.64,
            "mapping": {"slope": 1.0, "intercept": intercept},
        },
        path,
    )
    return path


def base_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-29",
        "season": "2026",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BOS",
        "market": "batter_hits",
        "side": "Over",
        "line": "0.5",
        "american_odds": "-110",
    }
    row.update(overrides)
    return row


def test_calibrated_verified_row_exposes_standard_trust_contract(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.6)
    write_calibration(settings, "batter_hits", intercept=0.02)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-29.csv",
        [base_row(source_row_id="row-1", prop_key="prop-1", game_pk="12345", book="FanDuel", attributionStatus="verified")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="features",
        dry_run=True,
    )
    row = report["rows"][0]

    assert row["calibrationStatus"] == "applied"
    assert row["calibrationBucket"].startswith("batter_hits|over|line:0-0.5")
    assert row["calibrationSampleSize"] == 250
    assert row["modelProbabilitySource"] == "calibrated_model"
    assert row["probabilityGuardrailStatus"] == "ok"
    assert row["trustTier"] == "standard"
    assert row["action"] == "Research"
    assert row["readinessLabel"] == "Experimental"
    assert row["stakeUnits"] == 0
    assert row["betActionAllowed"] is False
    assert report["summary"]["trustTierCounts"] == {"standard": 1}
    assert report["summary"]["guardrailStatusCounts"] == {"ok": 1}
    assert report["summary"]["calibrationCoverage"]["calibratedRows"] == 1
    assert report["summary"]["calibrationCoverage"]["calibrationStatusCountsByMarket"]["batter_hits"] == {"applied": 1}


def test_invalid_player_label_rows_remain_blocked_low_trust(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-29.csv",
        [
                base_row(
                    player="Over 1.5",
                    book="FanDuel",
                    source_row_id="row-1",
                    prop_key="prop-1",
                    game_pk="12345",
                attributionStatus="invalid_player_label",
            )
        ],
    )

    row = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="features",
        dry_run=True,
    )["rows"][0]

    assert row["trustTier"] == "blocked"
    assert row["trustScore"] < 25
    assert row["attributionBlockReason"] == "invalid_player_label"
    assert row["probabilityGuardrailStatus"] == "blocked"
    assert "invalid_player_label" in row["probabilityGuardrailReasons"]
    assert row["betActionAllowed"] is False


def test_missing_odds_skip_without_fake_probability_or_edge(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits")
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-29.csv", [base_row(american_odds="")])

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="features",
        dry_run=True,
    )

    assert report["rows"] == []
    assert report["summary"]["skipped_by_reason"] == {"bad_or_blank_odds": 1}
    assert report["summary"]["calibrationCoverage"]["sampleSkippedRows"][0]["reason"] == "bad_or_blank_odds"
    assert "modelProbabilityPercent" not in report["summary"]["calibrationCoverage"]["sampleSkippedRows"][0]
    assert "edgePercent" not in report["summary"]["calibrationCoverage"]["sampleSkippedRows"][0]


def test_fallback_only_context_does_not_upgrade_trust(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.6)
    write_calibration(settings, "batter_hits", intercept=0.02)
    _write_context_csv(
        settings.data_dir / "context" / "weather" / "weather_context_2026-06-29.csv",
        [{"game_pk": "12345", "fallbackReason": "slate_default"}],
    )
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-29.csv",
        [base_row(source_row_id="row-1", prop_key="prop-1", game_pk="12345", book="FanDuel", attributionStatus="verified")],
    )

    row = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="features",
        dry_run=True,
    )["rows"][0]

    assert row["contextReadinessStatus"] == "limited"
    assert "weather" in row["fallbackFeatureGroups"]
    assert row["trustTier"] != "high"
    assert "fallback_only_context" in row["trustReasons"] or "context_limited" in row["trustReasons"]


def test_data_status_exposes_model_trust_summaries(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    summary_path = settings.data_dir / "predictions" / "prop_predictions_2026-06-29_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "calibrationCoverage": {"totalScoredRows": 2, "calibratedRows": 1, "uncalibratedRows": 1},
                "trustTierCounts": {"standard": 1, "blocked": 1},
                "guardrailStatusCounts": {"ok": 1, "blocked": 1},
                "contextReadinessCounts": {"limited": 2},
                "sampleGuardrailRows": [{"player": "Example", "probabilityGuardrailStatus": "blocked"}],
                "sampleLowTrustRows": [{"player": "Example", "trustTier": "blocked"}],
                "sampleHighTrustRows": [{"player": "Verified", "trustTier": "standard"}],
                "sampleUncalibratedRows": [{"player": "Example", "calibrationStatus": "not_available"}],
            }
        ),
        encoding="utf-8",
    )

    payload = DataStatusService(
        settings=settings,
        now_provider=lambda: datetime(2026, 6, 29, 12, tzinfo=timezone.utc),
    ).payload({"season": ["2026"]})
    health = payload["playerboard_build_health"]

    assert health["calibrationCoverage"]["calibratedRows"] == 1
    assert health["trustTierCounts"] == {"standard": 1, "blocked": 1}
    assert health["guardrailStatusCounts"] == {"ok": 1, "blocked": 1}
    assert health["contextReadinessCounts"] == {"limited": 2}
    assert health["sampleUncalibratedRows"][0]["calibrationStatus"] == "not_available"


def _write_context_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
