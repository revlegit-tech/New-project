from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.backtest_dataset_builder_service import BacktestDatasetBuilderService
from mlb_app.services.backtest_readiness_service import BacktestReadinessService
from mlb_app.services.ml_feature_export_service import MLFeatureExportService
from mlb_app.services.ml_feature_schema import filter_safe_features
from mlb_app.services.player_prop_label_builder_service import PlayerPropLabelBuilderService, _StatLogs
from mlb_app.services.player_prop_label_schema import assert_label_not_in_features
from mlb_app.services.player_prop_market_stat_mapper import grade_over_under, market_to_stat_key


class FakeSnapshot:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = tuple(rows)


class FakePlayerboardService:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def snapshot_for_query(self, query: dict[str, list[str]]) -> FakeSnapshot:
        return FakeSnapshot(self.rows)

    def board_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {"status": "ok", "rows": self.rows, "top": self.rows}


class FakeEdgeBoardService:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {"status": "ok", "date": "2026-06-22", "season": 2026, "rows": self.rows}


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    values = {
        "root_dir": tmp_path,
        "public_dir": tmp_path / "public",
        "data_dir": data_dir,
        "model_dir": model_dir,
        "model_registry_path": model_dir / "model_registry.json",
        "current_season": 2026,
        "db_path": data_dir / "state.sqlite3",
        "db_enabled": False,
        "db_fallback_to_csv": True,
        "database_url": "",
    }
    values.update(overrides)
    return Settings(**values)


def prop_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-22",
        "season": 2026,
        "propKey": "judge-total-bases",
        "id": "row-1",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_total_bases",
        "rawLabel": "Over",
        "line": "1.5",
        "book": "ExampleBook",
        "americanOdds": "-110",
        "impliedProbabilityPercent": 52.38,
        "modelProbabilityPercent": 57.5,
        "hitRates": {"last_10": 0.6},
        "game_market_available": True,
        "game_market_game_id": "game-1",
        "game_market_consensus_open_total": 8.0,
        "game_market_consensus_current_total": 8.5,
        "game_market_total_line_movement": 0.5,
        "game_market_favorite_team_open": "NYY",
        "game_market_favorite_team_current": "NYY",
        "game_market_team_is_favorite_open": True,
        "game_market_team_is_favorite_current": True,
        "game_market_team_no_vig_win_prob_open": 0.58,
        "game_market_team_no_vig_win_prob_current": 0.61,
        "game_market_opponent_no_vig_win_prob_open": 0.42,
        "game_market_opponent_no_vig_win_prob_current": 0.39,
        "game_market_book_count_moneyline": 4,
        "game_market_book_count_total": 3,
        "game_market_book_count_runline": 2,
        "game_market_disagreement_score": 0.1,
        "game_market_team_moneyline_movement": -15,
        "game_market_opponent_moneyline_movement": 15,
        "game_market_quality_flags": ["ok"],
        "game_market_enrichment_status": "matched",
    }
    row.update(overrides)
    return row


def export_service(settings: Settings, rows: list[dict[str, Any]]) -> MLFeatureExportService:
    return MLFeatureExportService(
        settings=settings,
        playerboard_service=FakePlayerboardService(rows),
        edge_board_service=FakeEdgeBoardService(rows),
    )


def services(settings: Settings, rows: list[dict[str, Any]]) -> tuple[MLFeatureExportService, PlayerPropLabelBuilderService, BacktestDatasetBuilderService]:
    feature_service = export_service(settings, rows)
    label_service = PlayerPropLabelBuilderService(settings=settings, feature_export_service=feature_service)
    training_service = BacktestDatasetBuilderService(
        settings=settings,
        feature_export_service=feature_service,
        label_builder_service=label_service,
    )
    return feature_service, label_service, training_service


def app_with_services(settings: Settings, rows: list[dict[str, Any]]) -> TestClient:
    feature_service, label_service, training_service = services(settings, rows)
    container = AppContainer(settings=settings)
    container.ml_feature_export_service = feature_service
    container.player_prop_label_builder_service = label_service
    container.backtest_dataset_builder_service = training_service
    container.backtest_readiness_service = BacktestReadinessService(
        feature_export_service=feature_service,
        training_builder_service=training_service,
    )
    app = create_app(container=container)
    return TestClient(app, client=("127.0.0.1", 50000))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_batter_logs(settings: Settings, rows: list[dict[str, Any]]) -> None:
    write_csv(settings.data_dir / "cloud" / "season_logs" / "batter_game_logs_2026.csv", rows)


def write_pitcher_logs(settings: Settings, rows: list[dict[str, Any]]) -> None:
    write_csv(settings.data_dir / "cloud" / "season_logs" / "pitcher_game_logs_2026.csv", rows)


def write_feature_json(settings: Settings, date_label: str, rows: list[dict[str, Any]]) -> None:
    path = settings.data_dir / "warehouse" / "ml_features" / f"player_prop_features_{date_label}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")


def write_label_json(settings: Settings, date_label: str, rows: list[dict[str, Any]]) -> None:
    path = settings.data_dir / "warehouse" / "ml_labels" / f"player_prop_labels_{date_label}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")


def label_row(feature: dict[str, Any], *, result: str = "win", hit: bool = True) -> dict[str, Any]:
    return {
        "label_schema_version": "player-prop-labels.sprint13d.v1",
        "graded_at": "2026-06-23T00:00:00+00:00",
        "date": feature["date"],
        "season": feature["season"],
        "source_row_id": feature["source_row_id"],
        "prop_key": feature["prop_key"],
        "player": feature["player"],
        "team": feature["team"],
        "opponent": feature["opponent"],
        "market": feature["market"],
        "side": feature["side"],
        "line": feature["line"],
        "actual_value": 2 if hit else 0,
        "result": result,
        "hit": hit,
        "push": False,
        "void": False,
        "label_status": "graded",
        "label_reason": "synthetic",
        "stat_source": "test",
        "stat_key": "totalBases",
    }


def safe_features(settings: Settings, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return export_service(settings, rows).build_features(date_label="2026-06-22", source="edge-board").rows


def test_market_stat_mapper_maps_supported_markets_correctly() -> None:
    assert market_to_stat_key("batter_hits") == "hits"
    assert market_to_stat_key("batter_total_bases") == "totalBases"
    assert market_to_stat_key("pitcher_strikeouts_alt") == "strikeOuts"
    assert market_to_stat_key("pitcher_earned_runs") == "earnedRuns"


def test_unsupported_markets_return_unsupported_status(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    _, label_service, _ = services(settings, [prop_row(market="batter_unknown")])

    result = label_service.build_label_rows(date_label="2026-06-22", include_ungraded=True)

    assert result.rows[0]["label_status"] == "unsupported_market"
    assert result.rows[0]["result"] == "ungraded"


def test_over_under_grading_works_for_win_loss_push() -> None:
    assert grade_over_under(2, 1.5, "over")["result"] == "win"
    assert grade_over_under(1, 1.5, "over")["result"] == "loss"
    assert grade_over_under(1.5, 1.5, "over")["result"] == "push"
    assert grade_over_under(1, 1.5, "under")["result"] == "win"


def test_invalid_line_becomes_invalid_line(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(settings, [{"date": "2026-06-22", "player": "Aaron Judge", "team": "NYY", "totalBases": "3"}])
    _, label_service, _ = services(settings, [prop_row(line="abc")])

    result = label_service.build_label_rows(date_label="2026-06-22", include_ungraded=True)

    assert result.rows[0]["label_status"] == "invalid_line"


def test_missing_stat_becomes_missing_stat(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(settings, [{"date": "2026-06-22", "player": "Aaron Judge", "team": "NYY", "hits": "1"}])
    _, label_service, _ = services(settings, [prop_row()])

    result = label_service.build_label_rows(date_label="2026-06-22", include_ungraded=True)

    assert result.rows[0]["label_status"] == "missing_stat"


def test_stat_log_find_matches_full_team_name_to_abbreviation(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(settings, [{"date": "2026-06-22", "player": "Aaron Judge", "team": "NYY", "playerId": "592450", "hits": "2"}])
    logs = _StatLogs.load(settings, 2026)

    match = logs.find(market="batter_hits", date_label="2026-06-22", player="Aaron Judge", team="NEW YORK YANKEES")

    assert match.status == "ok"
    assert match.row["hits"] == "2"


def test_stat_log_find_falls_back_to_unique_player_when_feature_team_is_wrong(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(settings, [{"date": "2026-06-22", "player": "Vladimir Guerrero Jr.", "team": "TOR", "hits": "1"}])
    logs = _StatLogs.load(settings, 2026)

    match = logs.find(market="batter_hits", date_label="2026-06-22", player="Vladimir Guerrero Jr.", team="HOUSTON ASTROS")

    assert match.status == "ok"
    assert match.row["team"] == "TOR"


def test_stat_log_find_player_id_wins_with_team_mismatch(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(
        settings,
        [
            {"date": "2026-06-22", "player": "Same Name", "team": "NYY", "playerId": "111", "hits": "0"},
            {"date": "2026-06-22", "player": "Same Name", "team": "TOR", "playerId": "222", "hits": "2"},
        ],
    )
    logs = _StatLogs.load(settings, 2026)

    match = logs.find(market="batter_hits", date_label="2026-06-22", player="Same Name", team="HOUSTON ASTROS", player_id="222")

    assert match.status == "ok"
    assert match.row["team"] == "TOR"


def test_stat_log_find_strips_pitcher_market_suffix(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_pitcher_logs(settings, [{"date": "2026-06-22", "player": "Kodai Senga", "team": "NYM", "strikeOuts": "6"}])
    logs = _StatLogs.load(settings, 2026)

    match = logs.find(
        market="pitcher_strikeouts_alt",
        date_label="2026-06-22",
        player="Kodai Senga Strikeouts Thrown",
        team="CHICAGO CUBS",
        opponent="NEW YORK METS",
    )

    assert match.status == "ok"
    assert match.row["strikeOuts"] == "6"


def test_stat_log_find_duplicate_name_candidates_are_ambiguous(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(
        settings,
        [
            {"date": "2026-06-22", "player": "Duplicate Player", "team": "NYY", "hits": "1"},
            {"date": "2026-06-22", "player": "Duplicate Player", "team": "DET", "hits": "2"},
        ],
    )
    logs = _StatLogs.load(settings, 2026)

    match = logs.find(market="batter_hits", date_label="2026-06-22", player="Duplicate Player", team="HOUSTON ASTROS")

    assert match.status == "ambiguous_match"


def test_stat_log_find_truly_missing_player_returns_missing_player(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(settings, [{"date": "2026-06-22", "player": "Aaron Judge", "team": "NYY", "hits": "2"}])
    logs = _StatLogs.load(settings, 2026)

    match = logs.find(market="batter_hits", date_label="2026-06-22", player="Missing Player", team="NEW YORK YANKEES")

    assert match.status == "missing_player"


def test_label_builder_mixed_fixture_produces_hit_and_miss_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(
        settings,
        [
            {"date": "2026-06-22", "player": "Aaron Judge", "team": "NYY", "hits": "2"},
            {"date": "2026-06-22", "player": "Vladimir Guerrero Jr.", "team": "TOR", "hits": "0"},
        ],
    )
    _, label_service, _ = services(
        settings,
        [
            prop_row(propKey="judge-hits", id="judge-hits", player="Aaron Judge", team="NEW YORK YANKEES", market="batter_hits", line="0.5"),
            prop_row(
                propKey="vladdy-hits",
                id="vladdy-hits",
                player="Vladimir Guerrero Jr.",
                team="HOUSTON ASTROS",
                opponent="TORONTO BLUE JAYS",
                market="batter_hits",
                line="0.5",
            ),
        ],
    )

    result = label_service.build_label_rows(date_label="2026-06-22", include_ungraded=True)

    assert [row["label_status"] for row in result.rows] == ["graded", "graded"]
    assert [row["hit"] for row in result.rows] == [True, False]
    assert [row["result"] for row in result.rows] == ["hit", "miss"]


def test_label_builder_dry_run_does_not_write_files(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(settings, [{"date": "2026-06-22", "player": "Aaron Judge", "team": "NYY", "totalBases": "3"}])
    _, label_service, _ = services(settings, [prop_row()])
    output_dir = tmp_path / "labels"

    manifest = label_service.build_labels(date_label="2026-06-22", dry_run=True, output_dir=output_dir)

    assert manifest["row_count"] == 1
    assert not output_dir.exists()


def test_label_builder_writes_manifest_when_not_dry_run(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_batter_logs(settings, [{"date": "2026-06-22", "player": "Aaron Judge", "team": "NYY", "totalBases": "3"}])
    _, label_service, _ = services(settings, [prop_row()])
    output_dir = tmp_path / "labels"

    manifest = label_service.build_labels(date_label="2026-06-22", dry_run=False, output_dir=output_dir)

    assert manifest["written"] is True
    assert (output_dir / "player_prop_label_manifest_2026-06-22.json").exists()


def test_label_preview_endpoint_appears_in_openapi(tmp_path: Path) -> None:
    client = app_with_services(make_settings(tmp_path), [prop_row()])
    schema = client.app.openapi()

    assert "/api/ml-labels/preview" in schema["paths"]
    assert "/api/ml-training/preview" in schema["paths"]


def test_admin_label_build_endpoint_requires_action_header(tmp_path: Path) -> None:
    client = app_with_services(make_settings(tmp_path), [prop_row()])

    denied = client.post("/api/admin/ml-labels/build?date=2026-06-22&dryRun=true")
    allowed = client.post(
        "/api/admin/ml-labels/build?date=2026-06-22&dryRun=true",
        headers={"X-Baseball-Prop-Action": "1"},
    )

    assert denied.status_code == 403
    assert denied.json()["code"] == "action_header_required"
    assert allowed.status_code == 200


def test_admin_training_build_endpoint_requires_action_header(tmp_path: Path) -> None:
    client = app_with_services(make_settings(tmp_path), [prop_row()])

    denied = client.post("/api/admin/ml-training/build?date=2026-06-22&dryRun=true")
    allowed = client.post(
        "/api/admin/ml-training/build?date=2026-06-22&dryRun=true",
        headers={"X-Baseball-Prop-Action": "1"},
    )

    assert denied.status_code == 403
    assert denied.json()["code"] == "action_header_required"
    assert allowed.status_code == 200


def test_training_builder_joins_feature_rows_to_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    features = safe_features(settings, [prop_row()])
    write_label_json(settings, "2026-06-22", [label_row(features[0])])
    _, _, training_service = services(settings, [prop_row()])

    result = training_service.build_training_rows(date_label="2026-06-22", include_ungraded=True)

    assert result.manifest["joined_row_count"] == 1
    assert result.rows[0]["target_result"] == "win"


def test_training_output_target_fields_are_prefixed_and_blocked_fields_absent(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    features = safe_features(settings, [prop_row()])
    write_label_json(settings, "2026-06-22", [label_row(features[0])])
    _, _, training_service = services(settings, [prop_row()])

    row = training_service.build_training_rows(date_label="2026-06-22", include_ungraded=True).rows[0]

    assert {"target_result", "target_hit", "target_push", "target_actual_value", "target_label_status"} <= set(row)
    assert {"result", "hit", "push", "actual_value", "graded_at"}.isdisjoint(row)


def test_leakage_validation_fails_if_postgame_fields_appear_in_features(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    features = safe_features(settings, [prop_row()])
    leaky = dict(features[0]) | {"actual_value": 3, "result": "win", "hit": True, "profit_1u": 1.0}
    write_feature_json(settings, "2026-06-22", [leaky])
    write_label_json(settings, "2026-06-22", [label_row(features[0])])
    _, _, training_service = services(settings, [prop_row()])

    manifest = training_service.build_training_rows(date_label="2026-06-22", include_ungraded=True).manifest

    assert manifest["leakage_check_passed"] is False
    assert {"actual_value", "result", "hit", "profit_1u"} & set(manifest["blocked_feature_fields_found"])


def test_data_status_includes_label_and_training_sections(tmp_path: Path) -> None:
    client = app_with_services(make_settings(tmp_path), [prop_row()])

    response = client.get("/api/data/status?season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert "ml_label_exports" in payload
    assert "ml_training_datasets" in payload


def test_backtest_readiness_can_move_to_backtest_ready_with_two_class_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    raw_rows = [
        prop_row(propKey=f"row-{index}", id=f"row-{index}", line="1.5")
        for index in range(60)
    ]
    feature_rows = safe_features(settings, raw_rows)
    write_feature_json(settings, "2026-06-22", feature_rows)
    write_label_json(
        settings,
        "2026-06-22",
        [
            label_row(feature, result="win" if index % 2 == 0 else "loss", hit=index % 2 == 0)
            for index, feature in enumerate(feature_rows)
        ],
    )
    feature_service, _, training_service = services(settings, raw_rows)
    readiness = BacktestReadinessService(
        feature_export_service=feature_service,
        training_builder_service=training_service,
    )

    payload = readiness.evaluate(date_label="2026-06-22", source="edge-board")

    assert payload["markets"][0]["readiness"] == "backtest_ready"
    assert payload["markets"][0]["two_class_ready"] is True


def test_db_disabled_csv_fallback_mode_does_not_crash(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=False, db_fallback_to_csv=True)
    _, label_service, _ = services(settings, [prop_row()])

    manifest = label_service.build_labels(date_label="2026-06-22", dry_run=True, include_ungraded=True)

    assert manifest["status"] == "ok"


def test_openapi_builds(tmp_path: Path) -> None:
    client = app_with_services(make_settings(tmp_path), [prop_row()])
    schema = client.app.openapi()

    assert "/api/ml-labels/status" in schema["paths"]
    assert "/api/admin/ml-labels/build" in schema["paths"]
    assert "/api/admin/ml-training/build" in schema["paths"]


def test_regression_blocked_fields_removed_after_safe_export_and_target_prefixed(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    raw = prop_row(
        home_score=7,
        away_score=4,
        total_runs=11,
        home_win=True,
        profit_1u=1.0,
        actual_value=3,
        result="win",
        hit=True,
        push=False,
        graded_at="2026-06-23T00:00:00Z",
        closing_line_value=0.2,
    )
    feature = safe_features(settings, [raw])[0]
    assert {
        "home_score",
        "away_score",
        "total_runs",
        "home_win",
        "profit_1u",
        "actual_value",
        "result",
        "hit",
        "push",
        "graded_at",
        "closing_line_value",
    }.isdisjoint(feature)
    assert filter_safe_features(raw).get("actual_value") is None
    with pytest.raises(ValueError):
        assert_label_not_in_features({"player": "A", "actual_value": 2})

    write_label_json(settings, "2026-06-22", [label_row(feature)])
    _, _, training_service = services(settings, [raw])
    row = training_service.build_training_rows(date_label="2026-06-22", include_ungraded=True).rows[0]

    assert row["target_actual_value"] == 2
    assert {"actual_value", "result", "hit", "push", "graded_at"}.isdisjoint(row)
