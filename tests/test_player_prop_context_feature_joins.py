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
    settings.model_dir.mkdir(parents=True, exist_ok=True)
    for market in ("batter_hits", "pitcher_strikeouts"):
        path = settings.model_dir / f"prop_model_{market}.joblib"
        joblib.dump(TinyProbabilityModel(), path)
        metadata_path_for_model(path).write_text(
            json.dumps(
                {
                    "numericFeatures": [
                        "line",
                        "book_implied_probability",
                        "odds_move",
                        "line_move",
                        "recent_games",
                        "rolling_avg_5",
                        "pitcher_k_rate",
                        "pitcher_days_rest",
                        "barrel_rate",
                        "hard_hit_rate",
                        "batter_avg_vs_hand",
                        "batter_k_rate_vs_hand",
                    ]
                }
            ),
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


def player_form_context_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-30",
        "season": "2026",
        "player": "Aaron Judge",
        "team": "NYY",
        "recent_games": "10",
        "recent_rate": "1.2",
        "season_rate": "0.31",
        "rolling_avg_5": "1.4",
        "rolling_avg_10": "1.2",
        "rolling_avg_15": "1.1",
        "rolling_total_bases_10": "18",
        "rolling_hr_rate_15": "0.2",
        "rolling_k_rate_10": "0.22",
    }
    row.update(overrides)
    return row


def pitcher_context_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-30",
        "season": "2026",
        "pitcher": "Gerrit Cole",
        "team": "BOS",
        "pitcher_recent_games": "6",
        "pitcher_k_rate": "0.31",
        "pitcher_walk_rate": "0.08",
        "pitcher_hr_rate": "0.03",
        "pitcher_babip": "0.285",
        "pitcher_days_rest": "5",
        "pitcher_velo_delta": "",
    }
    row.update(overrides)
    return row


def statcast_context_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-30",
        "season": "2026",
        "player": "Aaron Judge",
        "team": "NYY",
        "barrel_rate": "0.14",
        "hard_hit_rate": "0.55",
        "xwoba": "0.41",
        "xba": "0.31",
        "xslg": "0.62",
        "batter_babip": "0.34",
        "batter_k_rate": "0.22",
        "batter_walk_rate": "0.11",
        "batter_ld_rate": "0.25",
        "batter_gb_rate": "0.39",
        "batter_sprint_speed": "27.4",
        "pregameSafe": "True",
        "labelsExcluded": "True",
    }
    row.update(overrides)
    return row


def platoon_context_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-30",
        "season": "2026",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BOS",
        "batter_hand": "R",
        "pitcher_hand": "L",
        "batter_avg_vs_hand": "0.3",
        "batter_k_rate_vs_hand": "0.2",
        "batter_recent_hits_vs_lhp": "4",
        "batter_recent_hits_vs_rhp": "7",
        "pitcher_avg_allowed_vs_hand": "0.25",
        "pregameSafe": "True",
        "labelsExcluded": "True",
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


def test_player_recent_form_joins_on_safe_identity(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "player_recent_form" / "player_recent_form_2026-06-30.csv",
        [player_form_context_row()],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    row = report["rows"][0]
    summary = report["summary"]
    assert row["recent_games"] == 10
    assert row["rolling_avg_5"] == 1.4
    assert summary["contextJoinCounts"]["playerRecentFormRowsLoaded"] == 1
    assert summary["contextJoinCounts"]["playerRecentFormRowsJoined"] == 1
    assert summary["featureCompleteness"]["player_recent_form"]["populatedPercent"] > 0


def test_pitcher_context_joins_on_safe_identity(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-30.csv",
        [base_row(player="Gerrit Cole Strikeouts Thrown", team="BOS", opponent="NYY", market="pitcher_strikeouts")],
    )
    write_csv(
        settings.data_dir / "context" / "pitcher_context" / "pitcher_context_2026-06-30.csv",
        [pitcher_context_row()],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    row = report["rows"][0]
    summary = report["summary"]
    assert row["subjectName"] == "Gerrit Cole"
    assert row["subjectRole"] == "pitcher"
    assert row["pitcher_k_rate"] == 0.31
    assert row["pitcher_days_rest"] == 5
    assert summary["contextJoinCounts"]["pitcherContextRowsLoaded"] == 1
    assert summary["contextJoinCounts"]["pitcherContextRowsJoined"] == 1
    assert summary["featureCompleteness"]["pitcher_context"]["populatedPercent"] > 0


def test_pitcher_context_skips_batter_rows_as_role_not_applicable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(pitcher="Gerrit Cole")])
    write_csv(
        settings.data_dir / "context" / "pitcher_context" / "pitcher_context_2026-06-30.csv",
        [pitcher_context_row()],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["pitcher_k_rate"] == ""
    assert report["summary"]["contextIdentityDiagnostics"]["pitcher_context"]["contextJoinSkipReasons"]["role_not_applicable"] == 1


def test_statcast_rows_join_on_safe_identity(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(settings.data_dir / "context" / "statcast" / "statcast_context_2026-06-30.csv", [statcast_context_row()])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    row = report["rows"][0]
    summary = report["summary"]
    assert row["barrel_rate"] == 0.14
    assert row["hard_hit_rate"] == 0.55
    assert summary["contextJoinCounts"]["statcastRowsLoaded"] == 1
    assert summary["contextJoinCounts"]["statcastRowsJoined"] == 1
    assert summary["featureCompleteness"]["statcast"]["populatedPercent"] > 0


def test_statcast_ambiguous_rows_skip_safely(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "statcast" / "statcast_context_2026-06-30.csv",
        [statcast_context_row(barrel_rate="0.14"), statcast_context_row(barrel_rate="0.2")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["barrel_rate"] == ""
    assert report["summary"]["contextJoinCounts"]["statcastAmbiguousRows"] == 2
    assert report["summary"]["contextJoinCounts"]["statcastRowsSkipped"] == 1


def test_handedness_platoon_rows_join_on_safe_identity(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row()],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    row = report["rows"][0]
    summary = report["summary"]
    assert row["batter_hand"] == "R"
    assert row["pitcher_hand"] == "L"
    assert row["batter_avg_vs_hand"] == 0.3
    assert row["pitcher_avg_allowed_vs_hand"] == 0.25
    assert summary["contextJoinCounts"]["handednessPlatoonRowsLoaded"] == 1
    assert summary["contextJoinCounts"]["handednessPlatoonRowsJoined"] == 1
    assert summary["featureCompleteness"]["handedness_platoon"]["populatedPercent"] > 0
    assert summary["contextIdentityDiagnostics"]["handedness_platoon"]["rowsJoined"] == 1
    assert summary["boardContextAlignmentDiagnostics"]["rowsWithSubjectTeam"] == 1
    assert summary["boardContextAlignmentDiagnostics"]["subjectRoleCounts"]["batter"] == 1


def test_handedness_platoon_skips_pitcher_rows_as_role_not_applicable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-30.csv",
        [base_row(player="Tarik Skubal Strikeouts Thrown", team="DET", opponent="HOU", market="pitcher_strikeouts")],
    )
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row(player="Tarik Skubal", team="DET", opponent="HOU")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["subjectName"] == "Tarik Skubal"
    assert report["rows"][0]["batter_avg_vs_hand"] == ""
    assert report["summary"]["contextIdentityDiagnostics"]["handedness_platoon"]["contextJoinSkipReasons"]["role_not_applicable"] == 1


def test_handedness_platoon_joins_when_team_aliases_normalize(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(player="Aaron Judge Jr.", team="New York Yankees")])
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row(player="Aaron Judge", team="NYY")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["batter_avg_vs_hand"] == 0.3
    assert report["summary"]["contextJoinCounts"]["handednessPlatoonRowsJoined"] == 1


def test_handedness_platoon_allows_missing_context_team_only_when_unique(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row(team="")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    diagnostics = report["summary"]["contextIdentityDiagnostics"]["handedness_platoon"]
    assert report["rows"][0]["batter_avg_vs_hand"] == 0.3
    assert diagnostics["rowsJoined"] == 1
    assert diagnostics["contextJoinSkipReasons"]["team_or_opponent_unavailable_but_key_unique"] == 1


def test_handedness_platoon_does_not_join_ambiguous_context_rows(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row(team=""), platoon_context_row(team="")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    diagnostics = report["summary"]["contextIdentityDiagnostics"]["handedness_platoon"]
    assert report["rows"][0]["batter_avg_vs_hand"] == ""
    assert report["summary"]["contextJoinCounts"]["handednessPlatoonAmbiguousRows"] == 2
    assert diagnostics["duplicateContextKeyRows"] == 2


def test_weak_identity_prevents_statcast_and_handedness_joins(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(team="")])
    write_csv(settings.data_dir / "context" / "statcast" / "statcast_context_2026-06-30.csv", [statcast_context_row()])
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row()],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    row = report["rows"][0]
    assert row["identityConfidence"] == "weak"
    assert row["barrel_rate"] == ""
    assert row["batter_avg_vs_hand"] == ""
    assert report["summary"]["contextJoinCounts"]["statcastRowsJoined"] == 0
    assert report["summary"]["contextJoinCounts"]["handednessPlatoonRowsJoined"] == 0


def test_context_identity_diagnostics_include_unmatched_samples(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(player="Juan Soto", source_row_id="row-2")])
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row(player="Aaron Judge")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    diagnostics = report["summary"]["contextIdentityDiagnostics"]["handedness_platoon"]
    assert diagnostics["noMatchRows"] == 1
    assert diagnostics["unmatchedScoringSamples"][0]["player"] == "Juan Soto"
    assert diagnostics["contextJoinKeyExamples"]


def test_handedness_artifact_rows_do_not_make_feature_ready_without_scoring_population(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(player="Juan Soto", source_row_id="row-2")])
    write_csv(
        settings.data_dir / "context" / "handedness_platoon" / "handedness_platoon_2026-06-30.csv",
        [platoon_context_row(player="Aaron Judge")],
    )

    summary = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)["summary"]

    assert summary["featureCompleteness"]["handedness_platoon"]["populatedPercent"] == 0
    assert "handedness_platoon" not in summary["featureGroupsReady"]
    assert "handedness_platoon" in summary["featureGroupsMissing"]
    assert any("handedness_platoon artifact has rows but no scoring rows joined safely" in warning for warning in summary["contextJoinWarnings"])


def test_ambiguous_player_recent_form_skips_safely(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row()])
    write_csv(
        settings.data_dir / "context" / "player_recent_form" / "player_recent_form_2026-06-30.csv",
        [player_form_context_row(recent_games="8"), player_form_context_row(recent_games="9")],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["recent_games"] == ""
    assert report["summary"]["contextJoinCounts"]["playerRecentFormAmbiguousRows"] == 2
    assert report["summary"]["contextJoinCounts"]["playerRecentFormRowsSkipped"] == 1


def test_weak_identity_prevents_recent_form_context_join(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-30.csv", [base_row(team="")])
    write_csv(
        settings.data_dir / "context" / "player_recent_form" / "player_recent_form_2026-06-30.csv",
        [player_form_context_row()],
    )

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    assert report["rows"][0]["identityConfidence"] == "weak"
    assert report["rows"][0]["recent_games"] == ""
    assert report["summary"]["contextJoinCounts"]["playerRecentFormRowsJoined"] == 0
    assert report["summary"]["featureCompleteness"]["player_recent_form"]["populatedPercent"] == 0
    assert any(
        "player_recent_form context artifact available but no scoring rows joined safely" in warning
        for warning in report["summary"]["contextJoinWarnings"]
    )


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
