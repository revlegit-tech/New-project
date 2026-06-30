from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import joblib

from mlb_app.config import Settings
from mlb_app.services.player_prop_model_runtime import metadata_path_for_model, score_exact_market_model
from mlb_app.services.player_prop_model_scoring_service import PlayerPropModelScoringService
from mlb_app.services.prop_side_normalization import normalize_prop_side


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


def playerboard_row(**overrides: Any) -> dict[str, Any]:
    row = base_row(
        american_odds="",
        americanOdds="-115",
        book="FanDuel",
        bookKey="fanduel",
        baseMarket="batter_hits",
        isAltMarket="false",
        rawLabel="Aaron Judge Over 0.5 Hits",
        confidence="",
        recommendation="",
        missingData="",
    )
    row.update(overrides)
    return row


def test_scores_rows_with_tiny_market_model_and_writes_outputs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    features = settings.data_dir / "features" / "prop_features_2026-06-29.csv"
    out = tmp_path / "predictions.csv"
    summary_out = tmp_path / "summary.json"
    write_csv(features, [base_row()])

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="features",
        out_path=out,
        summary_out_path=summary_out,
    )

    assert report["summary"]["rows_loaded"] == 1
    assert report["summary"]["rows_scored"] == 1
    assert report["summary"]["scored_by_market"] == {"batter_hits": 1}
    assert report["rows"][0]["modelProbabilityPercent"] == 62
    assert report["rows"][0]["action"] == "Research"
    assert out.exists()
    assert summary_out.exists()


def test_playerboard_source_loads_playerboard_not_features(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    write_csv(settings.data_dir / "features" / "prop_features_2026-06-29.csv", [base_row(player="Feature Player")])
    playerboard = settings.data_dir / "playerboard" / "playerboard_2026.csv"
    write_csv(playerboard, [playerboard_row(player="Board Player")])

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="playerboard",
        dry_run=True,
    )

    assert report["summary"]["inputSource"] == "playerboard"
    assert report["summary"]["inputPath"] == str(playerboard)
    assert report["summary"]["rowsLoaded"] == 1
    assert report["rows"][0]["player"] == "Board Player"


def test_playerboard_prediction_preserves_identity_and_generates_strong_key(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    write_csv(settings.data_dir / "playerboard" / "playerboard_2026.csv", [playerboard_row()])

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="playerboard",
        dry_run=True,
    )
    row = report["rows"][0]

    assert row["team"] == "NYY"
    assert row["opponent"] == "BOS"
    assert row["book"] == "FanDuel"
    assert row["bookKey"] == "fanduel"
    assert row["rawLabel"] == "Aaron Judge Over 0.5 Hits"
    assert row["predictionKey"] == "2026-06-29|batter_hits|aaron_judge|nyy|bos|fanduel|0.5|over|-115"
    assert row["joinKeyStrength"] == "strong"
    assert row["warnings"] == ""


def test_playerboard_side_is_derived_from_raw_label_when_side_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [playerboard_row(side="", rawLabel="Aaron Judge Under 1.5 Hits", line="1.5")],
    )

    row = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="playerboard",
        dry_run=True,
    )["rows"][0]

    assert row["side"] == "Under"
    assert row["modelProbabilityPercent"] == 38


def test_prop_side_normalization_uses_canonical_over_under_sources() -> None:
    assert normalize_prop_side("", "Aaron Judge Over 0.5 Hits", "", "") == "Over"
    assert normalize_prop_side("", "", "Under 1.5 total bases", "") == "Under"
    assert normalize_prop_side("", "", "", "UNDER") == "Under"


def test_prop_side_normalization_preserves_unknown_and_malformed_values() -> None:
    assert normalize_prop_side("", "Aaron Judge 1.5 Hits", "", "") == ""
    assert normalize_prop_side("Yes", "", "", "") == "Yes"


def test_playerboard_prediction_key_is_deterministic(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    write_csv(settings.data_dir / "playerboard" / "playerboard_2026.csv", [playerboard_row()])
    service = PlayerPropModelScoringService(settings=settings)

    first = service.score(date_label="2026-06-29", season=2026, source="playerboard", dry_run=True)["rows"][0]
    second = service.score(date_label="2026-06-29", season=2026, source="playerboard", dry_run=True)["rows"][0]

    assert first["predictionKey"] == second["predictionKey"]


def test_playerboard_missing_team_or_opponent_warns(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    write_csv(settings.data_dir / "playerboard" / "playerboard_2026.csv", [playerboard_row(team="", opponent="BOS")])

    row = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="playerboard",
        dry_run=True,
    )["rows"][0]

    assert row["joinKeyStrength"] == "medium"
    assert "missing_team_or_opponent" in row["warnings"]


def test_runtime_scores_exact_market_model_with_metadata(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    model_path = write_model(settings, "batter_hits", probability=0.64)
    metadata_path_for_model(model_path).write_text(
        json.dumps({"bestModel": "tiny-fixture", "numericFeatures": ["line", "book_implied_probability"]}),
        encoding="utf-8",
    )

    prediction = score_exact_market_model(base_row(), market="batter_hits", settings=settings)

    assert prediction.probability == 0.64
    assert prediction.model_version == "tiny-fixture"
    assert prediction.model_path == model_path
    assert prediction.features_used[:2] == ["line", "book_implied_probability"]


def test_missing_model_skips_safely(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    features = settings.data_dir / "features" / "prop_features_2026-06-29.csv"
    write_csv(features, [base_row(market="pitcher_strikeouts")])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-29", season=2026, source="features", dry_run=True)

    assert report["summary"]["rows_scored"] == 0
    assert report["summary"]["rows_skipped"] == 1
    assert report["summary"]["rowsSkipped"] == 1
    assert report["summary"]["skipped_by_reason"] == {"missing_model": 1}
    assert report["summary"]["missing_model_markets"] == ["pitcher_strikeouts"]


def test_bad_or_blank_odds_skip_safely(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits")
    features = settings.data_dir / "features" / "prop_features_2026-06-29.csv"
    write_csv(features, [base_row(american_odds=""), base_row(player="Juan Soto", american_odds="not-odds")])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-29", season=2026, source="features", dry_run=True)

    assert report["summary"]["rows_scored"] == 0
    assert report["summary"]["rows_skipped"] == 2
    assert report["summary"]["skipped_by_reason"] == {"bad_or_blank_odds": 2}
    assert report["summary"]["errors"] == []


def test_outputs_remain_research_only_with_zero_stake(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.8)
    features = settings.data_dir / "features" / "prop_features_2026-06-29.csv"
    write_csv(features, [base_row()])

    row = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-29", season=2026, source="features", dry_run=True)["rows"][0]

    assert row["readinessLabel"] == "Experimental"
    assert row["action"] == "Research"
    assert row["stake"] == 0
    assert row["stakeUnits"] == 0


def test_feature_source_blank_identity_fields_are_marked_unsafe(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits", probability=0.62)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-29.csv",
        [base_row(source_row_id="", prop_key="", game_pk="", team="", opponent="")],
    )

    row = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="features",
        dry_run=True,
    )["rows"][0]

    assert row["joinKeyStrength"] == "unsafe"
    assert "unsafe_prediction_join_key" in row["warnings"]
    assert row["source_row_id"] == ""
    assert row["prop_key"] == ""
    assert row["game_pk"] == ""


def test_dry_run_does_not_write_prediction_artifacts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings, "batter_hits")
    features = settings.data_dir / "features" / "prop_features_2026-06-29.csv"
    out = tmp_path / "predictions.csv"
    summary_out = tmp_path / "summary.json"
    write_csv(features, [base_row()])

    report = PlayerPropModelScoringService(settings=settings).score(
        date_label="2026-06-29",
        season=2026,
        source="features",
        out_path=out,
        summary_out_path=summary_out,
        dry_run=True,
    )

    assert report["summary"]["dry_run"] is True
    assert report["summary"]["rows_scored"] == 1
    assert not out.exists()
    assert not summary_out.exists()
