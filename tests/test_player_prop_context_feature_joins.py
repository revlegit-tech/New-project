from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import joblib

from mlb_app.config import Settings
from mlb_app.services.player_prop_context_feature_join_service import PlayerPropContextFeatureJoinService
from mlb_app.services.player_prop_model_runtime import metadata_path_for_model
from mlb_app.services.player_prop_model_scoring_service import PlayerPropModelScoringService


class TinyProbabilityModel:
    def predict_proba(self, matrix: Any) -> list[list[float]]:
        return [[0.4, 0.6] for _ in range(len(matrix))]


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
    fields = fieldnames or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_model(settings: Settings) -> None:
    path = settings.model_dir / "prop_model_batter_hits.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(TinyProbabilityModel(), path)
    metadata_path_for_model(path).write_text(
        json.dumps({"numericFeatures": ["line", "book_implied_probability", "odds_move", "line_move"]}),
        encoding="utf-8",
    )


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
        "book": "FanDuel",
        "bookKey": "fanduel",
        "american_odds": "-110",
        "source_row_id": "row-1",
        "prop_key": "prop-1",
        "game_pk": "123",
    }
    row.update(overrides)
    return row


def odds_context_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-30",
        "season": "2026",
        "player": "Aaron Judge",
        "market": "batter_hits",
        "side": "Over",
        "line": "0.5",
        "book": "FanDuel",
        "bookKey": "fanduel",
        "odds_move": "15",
        "line_move": "1",
    }
    row.update(overrides)
    return row


def test_odds_movement_artifact_loads(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    path = settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv"
    write_csv(path, [odds_context_row()])

    artifacts = PlayerPropContextFeatureJoinService(settings).load_artifacts(date_label="2026-06-30")

    assert artifacts["odds_movement"]["exists"] is True
    assert artifacts["odds_movement"]["rows"] == 1
    assert {"odds_move", "line_move"} <= set(artifacts["odds_movement"]["fields"])


def test_odds_movement_joins_on_unique_safe_key(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv", [odds_context_row()])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    row = report["rows"][0]
    summary = report["summary"]
    assert row["odds_move"] == 15
    assert row["line_move"] == 1
    assert summary["contextJoinCounts"]["oddsMovementRowsLoaded"] == 1
    assert summary["contextJoinCounts"]["oddsMovementRowsJoined"] == 1
    assert summary["oddsMovementRowsJoined"] == 1


def test_odds_movement_does_not_join_ambiguous_key(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv",
        [odds_context_row(odds_move="15"), odds_context_row(odds_move="20")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["odds_move"] == ""
    assert report["summary"]["contextJoinCounts"]["oddsMovementAmbiguousRows"] == 2
    assert report["summary"]["contextJoinCounts"]["skippedByReason"]["ambiguous_match"] == 1


def test_odds_movement_does_not_join_when_side_is_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(side="", rawLabel="")])
    write_csv(settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv", [odds_context_row()])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["odds_move"] == ""
    assert report["summary"]["contextJoinCounts"]["skippedByReason"]["missing_side"] == 1


def test_odds_movement_does_not_join_for_weak_identity(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(team="")])
    write_csv(settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv", [odds_context_row()])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["identityConfidence"] == "weak"
    assert report["rows"][0]["odds_move"] == ""
    assert report["summary"]["contextJoinCounts"]["skippedByReason"]["weak_or_unknown_identity"] == 1


def test_feature_completeness_reflects_actual_joined_odds_movement(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-30.csv",
        [base_row(player="Aaron Judge", source_row_id="row-1"), base_row(player="Juan Soto", source_row_id="row-2")],
    )
    write_csv(settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv", [odds_context_row()])

    summary = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)["summary"]

    odds = summary["featureCompleteness"]["odds_movement"]
    assert odds["availableFields"] == ["odds_move", "line_move"]
    assert odds["populatedPercent"] == 50
    assert "odds_movement" in summary["featureGroupsReady"]


def test_missing_context_files_warn_but_do_not_crash(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["summary"]["rowsScored"] == 1
    assert report["summary"]["contextFeatureArtifacts"]["odds_movement"]["exists"] is False
    assert any("odds_movement context artifact missing" in warning for warning in report["summary"]["contextJoinWarnings"])


def test_empty_context_file_warns_but_does_not_crash(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv",
        [],
        fieldnames=["date", "season", "player", "market", "side", "line", "bookKey", "odds_move", "line_move"],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["summary"]["rowsScored"] == 1
    assert report["summary"]["contextJoinCounts"]["oddsMovementRowsLoaded"] == 0
    assert any("odds_movement context artifact loaded with 0 rows" in warning for warning in report["summary"]["contextJoinWarnings"])


def test_context_join_summary_preserves_research_lock(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv", [odds_context_row()])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    summary = report["summary"]
    row = report["rows"][0]
    assert "contextJoinCounts" in summary
    assert "contextJoinWarnings" in summary
    assert row["readinessLabel"] == "Experimental"
    assert row["action"] == "Research"
    assert row["stakeUnits"] == 0
    assert row["betActionAllowed"] is False
