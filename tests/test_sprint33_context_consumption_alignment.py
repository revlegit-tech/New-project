from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import joblib

from mlb_app.config import Settings
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.player_prop_model_runtime import metadata_path_for_model
from mlb_app.services.player_prop_model_scoring_service import PlayerPropModelScoringService


class TinyProbabilityModel:
    def predict_proba(self, matrix: Any) -> list[list[float]]:
        return [[0.38, 0.62] for _ in range(len(matrix))]


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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def write_model(settings: Settings, numeric_features: list[str]) -> None:
    path = settings.model_dir / "prop_model_batter_hits.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(TinyProbabilityModel(), path)
    metadata_path_for_model(path).write_text(json.dumps({"numericFeatures": numeric_features}), encoding="utf-8")


def base_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-30",
        "season": "2026",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BOS",
        "market": "batter_hits",
        "side": "Over",
        "line": "0.5",
        "american_odds": "-110",
        "source_row_id": "row-1",
        "prop_key": "prop-1",
        "game_pk": "123",
    }
    row.update(overrides)
    return row


def score_summary(tmp_path: Path, *, numeric_features: list[str]) -> dict[str, Any]:
    settings = make_settings(tmp_path)
    write_model(settings, numeric_features)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    return PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )["summary"]


def test_game_markets_artifact_exists_without_populated_model_fields_is_not_generic_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, ["line", "book_implied_probability", "game_market_consensus_current_total"])
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "game_markets" / "game_markets_2026-06-30.csv",
        [{"date": "2026-06-30", "game_id": "123", "consensus_current_total": "8.5"}],
    )

    summary = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )["summary"]
    payload = summary["contextConsumption"]["game_markets"]

    assert payload["artifactExists"] is True
    assert payload["artifactRows"] == 1
    assert payload["configuredForCurrentModel"] is True
    assert payload["usedByCurrentModel"] is False
    assert payload["populatedFeatureFields"] == []
    assert payload["status"] == "artifact_only"
    assert "join into scoring/model features" in payload["reason"]
    assert "game_markets" in summary["featureGroupsMissing"]


def test_statcast_zero_safe_rows_reports_no_safe_rows_without_fabrication(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, ["line", "book_implied_probability", "barrel_rate"])
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "statcast" / "statcast_context_2026-06-30.csv",
        [],
        fieldnames=["date", "player", "barrel_rate", "hard_hit_rate", "player_mlbam_id"],
    )

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )
    payload = report["summary"]["contextConsumption"]["statcast"]

    assert payload["artifactExists"] is True
    assert payload["artifactRows"] == 0
    assert payload["configuredForCurrentModel"] is True
    assert payload["usedByCurrentModel"] is False
    assert payload["status"] == "no_safe_rows"
    assert "safe identity" in payload["reason"] or "safe local rows" in payload["reason"]
    assert report["rows"][0]["barrel_rate"] == ""
    assert "player_mlbam_id" not in report["rows"][0]


def test_weather_artifact_exists_but_current_model_does_not_consume_it(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, ["line", "book_implied_probability"])
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "weather" / "weather_context_2026-06-30.csv",
        [{"date": "2026-06-30", "temperature": "72", "wind_mph": "8"}],
    )

    summary = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )["summary"]
    payload = summary["contextConsumption"]["weather"]

    assert payload["artifactExists"] is True
    assert payload["configuredForCurrentModel"] is False
    assert payload["usedByCurrentModel"] is False
    assert payload["status"] == "available_not_used"
    assert "current model metadata does not consume" in payload["reason"]
    assert "weather" not in summary["featureGroupsMissing"]


def test_umpire_artifact_exists_but_current_model_does_not_consume_it(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, ["line", "book_implied_probability"])
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "umpire" / "umpire_context_2026-06-30.csv",
        [{"date": "2026-06-30", "umpire": "", "ump_k_rate": ""}],
    )

    summary = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )["summary"]
    payload = summary["contextConsumption"]["umpire"]

    assert payload["artifactExists"] is True
    assert payload["configuredForCurrentModel"] is False
    assert payload["usedByCurrentModel"] is False
    assert payload["status"] == "available_not_used"
    assert "umpire" not in summary["featureGroupsMissing"]


def test_bullpen_artifact_exists_with_join_pending_is_artifact_only_or_available_not_used(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, ["line", "book_implied_probability"])
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "bullpen" / "bullpen_context_2026-06-30.csv",
        [{"date": "2026-06-30", "team": "BOS", "opponent_bullpen_era_7d": "3.75"}],
    )

    summary = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )["summary"]
    payload = summary["contextConsumption"]["bullpen_context"]

    assert payload["artifactExists"] is True
    assert payload["rowsJoinedToScoring"] == 0
    assert payload["configuredForCurrentModel"] is False
    assert payload["usedByCurrentModel"] is False
    assert payload["status"] in {"artifact_only", "available_not_used"}
    assert "bullpen_context" not in summary["featureGroupsMissing"]


def test_feature_groups_missing_only_tracks_current_model_required_groups(tmp_path: Path) -> None:
    summary = score_summary(tmp_path, numeric_features=["line", "book_implied_probability", "barrel_rate"])

    assert "statcast" in summary["featureGroupsMissing"]
    assert "weather" not in summary["featureGroupsMissing"]
    assert "umpire" not in summary["featureGroupsMissing"]
    assert summary["contextConsumption"]["statcast"]["configuredForCurrentModel"] is True
    assert summary["contextConsumption"]["statcast"]["usedByCurrentModel"] is False
    assert summary["contextConsumption"]["weather"]["usedByCurrentModel"] is False
    assert summary["contextConsumption"]["umpire"]["usedByCurrentModel"] is False


def test_direct_scoring_model_fields_mark_group_used_without_artifact_join(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, ["line", "book_implied_probability", "odds_move", "line_move"])
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-30.csv",
        [base_row(line="1.5", american_odds="-105", previous_line="0.5", previous_american_odds="-120")],
    )

    summary = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )["summary"]
    payload = summary["contextConsumption"]["odds_movement"]

    assert payload["configuredForCurrentModel"] is True
    assert payload["usedByCurrentModel"] is True
    assert payload["status"] == "used"
    assert payload["rowsJoinedToScoring"] == 1
    assert "odds_movement" in summary["featureGroupsReady"]
    assert "odds_movement" not in summary["featureGroupsMissing"]


def test_context_consumption_keeps_backward_compatible_summary_keys(tmp_path: Path) -> None:
    summary = score_summary(tmp_path, numeric_features=["line", "book_implied_probability"])

    for key in (
        "contextFeatureArtifacts",
        "featureCompleteness",
        "featureGroupsReady",
        "featureGroupsMissing",
        "contextJoinCounts",
        "contextConsumption",
    ):
        assert key in summary
    assert "game_markets" in summary["contextConsumption"]


def test_context_consumption_does_not_fabricate_context_values_or_postgame_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, ["line", "book_implied_probability", "temperature", "ump_k_rate", "opponent_bullpen_era_7d"])
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(settings.data_dir / "context" / "weather" / "weather_context_2026-06-30.csv", [{"date": "2026-06-30"}])
    write_csv(settings.data_dir / "context" / "umpire" / "umpire_context_2026-06-30.csv", [{"date": "2026-06-30"}])
    write_csv(settings.data_dir / "context" / "bullpen" / "bullpen_context_2026-06-30.csv", [{"date": "2026-06-30"}])

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-30",
        season=2026,
        source="features",
        dry_run=True,
    )
    row = report["rows"][0]

    for field in ("temperature", "wind_mph", "ump_k_rate", "opponent_bullpen_era_7d", "actual_value", "grade"):
        assert row.get(field, "") == ""
    assert row["action"] == "Research"
    assert row["readinessLabel"] == "Experimental"
    assert row["stakeUnits"] == 0
    assert row["betActionAllowed"] is False


def test_data_status_exposes_context_consumption_under_playerboard_build_health(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    summary_path = settings.data_dir / "predictions" / "prop_predictions_2026-06-30_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "contextConsumption": {
                    "game_markets": {
                        "artifactExists": True,
                        "artifactRows": 1,
                        "artifactPath": "data/context/game_markets/game_markets_2026-06-30.csv",
                        "rowsLoaded": 1,
                        "rowsJoinedToScoring": 0,
                        "populatedFeatureFields": [],
                        "missingFeatureFields": ["game_market_consensus_current_total"],
                        "populatedPercent": 0.0,
                        "configuredForCurrentModel": True,
                        "usedByCurrentModel": False,
                        "modelFeatureFields": ["game_market_consensus_current_total"],
                        "status": "artifact_only",
                        "reason": "Artifact exists, but join into scoring/model features is pending or not implemented.",
                        "warnings": [],
                    }
                },
                "contextFeatureArtifacts": {"game_markets": {"exists": True, "rows": 1}},
                "contextJoinCounts": {},
                "featureCompleteness": {},
                "featureGroupsReady": [],
                "featureGroupsMissing": ["game_markets"],
            }
        ),
        encoding="utf-8",
    )

    payload = DataStatusService(settings=settings).payload({"season": ["2026"]})
    health = payload["playerboard_build_health"]

    assert "playerboard" not in payload
    assert health["contextConsumption"]["game_markets"]["configuredForCurrentModel"] is True
    assert health["contextConsumption"]["game_markets"]["usedByCurrentModel"] is False
    assert health["contextFeatureArtifacts"]["game_markets"]["exists"] is True
    assert health["contextJoinCounts"] == {}
    assert health["featureGroupsMissing"] == ["game_markets"]
