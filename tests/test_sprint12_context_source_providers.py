from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import joblib

from mlb_app.config import Settings
from mlb_app.services.context_sources.base import ContextProviderResult
from mlb_app.services.context_sources.mlb_stats_context_provider import MLBStatsContextProvider
from mlb_app.services.context_sources.odds_movement_context_provider import OddsMovementContextProvider
from mlb_app.services.context_sources.umpire_context_provider import UmpireContextProvider
from mlb_app.services.context_sources.weather_context_provider import WeatherContextProvider
from mlb_app.services.feature_source_audit_service import FeatureSourceAuditService
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


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_model(settings: Settings) -> None:
    path = settings.model_dir / "prop_model_batter_hits.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(TinyProbabilityModel(), path)
    metadata_path_for_model(path).write_text(
        json.dumps({"numericFeatures": ["line", "book_implied_probability", "recent_games", "pitcher_k_rate", "odds_move"]}),
        encoding="utf-8",
    )


def test_provider_result_contract_serializes_required_fields() -> None:
    result = ContextProviderResult(status="ok", date="2026-06-30", season=2026, source="fixture", rows=1, path="artifact.csv")

    payload = result.to_dict()

    for key in [
        "status",
        "date",
        "season",
        "source",
        "rows",
        "path",
        "generatedAt",
        "externalApiCallsMade",
        "pregameSafe",
        "labelsExcluded",
        "warnings",
        "errors",
    ]:
        assert key in payload
    assert payload["externalApiCallsMade"] == 0
    assert payload["pregameSafe"] is True
    assert payload["labelsExcluded"] is True


def test_local_season_logs_produce_player_recent_form_without_same_day_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "cloud" / "season_logs" / "batter_game_logs_2026.csv",
        [
            {"date": "2026-06-28", "season": "2026", "player": "Aaron Judge", "team": "NYY", "atBats": "4", "hits": "2", "homeRuns": "1", "strikeOuts": "1", "plateAppearances": "5", "totalBases": "5"},
            {"date": "2026-06-30", "season": "2026", "player": "Aaron Judge", "team": "NYY", "atBats": "5", "hits": "5", "homeRuns": "2", "strikeOuts": "0", "plateAppearances": "5", "totalBases": "11"},
        ],
    )

    result = MLBStatsContextProvider(settings).player_recent_form(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.status == "ok"
    assert result.rows == 1
    assert rows[0]["player"] == "Aaron Judge"
    assert rows[0]["recent_games"] == "1"
    assert rows[0]["rolling_total_bases_10"] == "5.0"
    assert "result" not in rows[0]
    assert "label" not in rows[0]


def test_local_pitcher_logs_produce_pitcher_context(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "cloud" / "season_logs" / "pitcher_game_logs_2026.csv",
        [
            {"date": "2026-06-27", "season": "2026", "player": "Gerrit Cole", "team": "NYY", "battersFaced": "25", "strikeOuts": "8", "baseOnBalls": "2", "homeRuns": "1", "hits": "5", "inningsPitched": "6"},
        ],
    )

    result = MLBStatsContextProvider(settings).pitcher_context(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.status == "ok"
    assert rows[0]["pitcher"] == "Gerrit Cole"
    assert rows[0]["pitcher_k_rate"] == "0.32"
    assert rows[0]["pitcher_days_rest"] == "3"


def test_odds_snapshots_produce_odds_movement(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    prior = {"date": "2026-06-29", "player": "Aaron Judge", "market": "batter_hits", "side": "Over", "line": "0.5", "bookKey": "fanduel", "book": "FanDuel", "americanOdds": "-120"}
    current = {**prior, "date": "2026-06-30", "americanOdds": "-105"}
    write_csv(settings.data_dir / "odds" / "propline_props_2026-06-29.csv", [prior])
    write_csv(settings.data_dir / "odds" / "propline_props_2026-06-30.csv", [current])

    result = OddsMovementContextProvider(settings).materialize(date_label="2026-06-30", season=2026)
    rows = read_csv(Path(result.path))

    assert result.status == "ok"
    assert rows[0]["previousAmericanOdds"] == "-120"
    assert rows[0]["odds_move"] == "15.0"


def test_missing_prior_odds_snapshot_warns_without_failure(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(settings.data_dir / "odds" / "propline_props_2026-06-30.csv", [{"player": "Aaron Judge", "market": "batter_hits", "side": "Over", "line": "0.5", "bookKey": "fanduel", "americanOdds": "-105"}])

    result = OddsMovementContextProvider(settings).materialize(date_label="2026-06-30", season=2026)

    assert result.status == "partial"
    assert result.rows == 1
    assert "Prior odds snapshot not found; movement fields left null." in result.warnings


def test_weather_provider_returns_missing_safely_without_configured_source(tmp_path: Path) -> None:
    result = WeatherContextProvider(make_settings(tmp_path)).materialize(date_label="2026-06-30", season=2026)

    assert result.status == "missing"
    assert result.externalApiCallsMade == 0
    assert result.pregameSafe is True
    assert "external weather calls skipped" in result.warnings[0]


def test_umpire_provider_uses_neutral_fallback(tmp_path: Path) -> None:
    result = UmpireContextProvider(make_settings(tmp_path)).materialize(date_label="2026-06-30", season=2026)

    assert result.status == "neutral_fallback"
    assert result.rows == 0
    assert result.criticalForBoard is False
    assert result.warnings == ["Umpire context unavailable; neutral fallback used."]


def test_context_audit_summary_includes_all_providers(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(settings.data_dir / "cloud" / "season_logs" / "batter_game_logs_2026.csv", [{"date": "2026-06-28", "player": "Aaron Judge", "team": "NYY", "atBats": "4", "hits": "2"}])
    write_csv(settings.data_dir / "cloud" / "season_logs" / "pitcher_game_logs_2026.csv", [{"date": "2026-06-28", "player": "Gerrit Cole", "team": "NYY", "battersFaced": "20", "strikeOuts": "7"}])
    write_csv(settings.data_dir / "odds" / "propline_props_2026-06-30.csv", [{"player": "Aaron Judge", "market": "batter_hits", "side": "Over", "line": "0.5", "bookKey": "fanduel", "americanOdds": "-105"}])

    audit = FeatureSourceAuditService(settings).materialize(date_label="2026-06-30", season=2026)

    expected = {"player_recent_form", "pitcher_context", "odds_movement", "game_markets", "weather", "statcast", "bullpen_context", "umpire"}
    assert set(audit["providers"]) == expected
    assert audit["externalApiCallsMade"] == 0
    assert audit["pregameSafe"] is True
    assert Path(audit["path"]).is_file()


def test_feature_completeness_detects_context_artifacts_and_research_lock_stays_intact(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_model(settings)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-30.csv",
        [{"date": "2026-06-30", "player": "Aaron Judge", "team": "NYY", "opponent": "BOS", "market": "batter_hits", "side": "Over", "line": "0.5", "american_odds": "-110", "source_row_id": "row-1", "prop_key": "prop-1", "game_pk": "123"}],
    )
    write_csv(settings.data_dir / "context" / "player_recent_form" / "player_recent_form_2026-06-30.csv", [{"date": "2026-06-30", "player": "Aaron Judge", "recent_games": "5"}])
    write_csv(settings.data_dir / "context" / "pitcher_context" / "pitcher_context_2026-06-30.csv", [{"date": "2026-06-30", "pitcher": "Gerrit Cole", "pitcher_k_rate": "0.31"}])
    write_csv(settings.data_dir / "context" / "odds_movement" / "odds_movement_2026-06-30.csv", [{"date": "2026-06-30", "player": "Aaron Judge", "odds_move": "15"}])

    report = PlayerPropModelScoringService(settings=settings).score(date_label="2026-06-30", season=2026, source="features", dry_run=True)

    summary = report["summary"]
    row = report["rows"][0]
    assert {"player_recent_form", "pitcher_context", "odds_movement"} <= set(summary["featureGroupsReady"])
    assert summary["contextFeatureArtifacts"]["player_recent_form"]["rows"] == 1
    assert row["action"] == "Research"
    assert row["stakeUnits"] == 0
    assert row["betActionAllowed"] is False
