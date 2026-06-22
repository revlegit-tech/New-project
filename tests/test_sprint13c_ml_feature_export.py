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
from mlb_app.services.backtest_readiness_service import BacktestReadinessService
from mlb_app.services.ml_feature_export_service import MLFeatureExportService
from mlb_app.services.ml_feature_schema import (
    assert_no_leakage_fields,
    blocked_feature_names,
    filter_safe_features,
    safe_game_market_feature_names,
)


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


def app_with_service(settings: Settings, service: MLFeatureExportService) -> TestClient:
    container = AppContainer(settings=settings)
    container.ml_feature_export_service = service
    container.backtest_readiness_service = BacktestReadinessService(feature_export_service=service)
    app = create_app(container=container)
    return TestClient(app, client=("127.0.0.1", 50000))


def test_safe_feature_schema_includes_sprint13b_game_market_fields() -> None:
    names = set(safe_game_market_feature_names())

    assert "game_market_consensus_current_total" in names
    assert "game_market_team_no_vig_win_prob_current" in names
    assert "game_market_disagreement_score" in names
    assert "game_market_enrichment_status" in names


def test_leakage_fields_are_blocked() -> None:
    blocked = blocked_feature_names()

    assert {"home_score", "away_score", "profit_1u", "result", "closing_line_value"} <= blocked


def test_assert_no_leakage_fields_raises_on_outcome_profit_fields() -> None:
    with pytest.raises(ValueError):
        assert_no_leakage_fields({"player": "Leak", "home_score": 4, "result": "win", "profit_1u": 1.0})


def test_export_service_filters_unsafe_fields(tmp_path: Path) -> None:
    row = prop_row(home_score=5, away_score=4, profit_1u=1.0, result="win", closing_line_value=0.12)

    filtered = export_service(make_settings(tmp_path), [row]).build_features(
        date_label="2026-06-22",
        source="edge-board",
    ).rows[0]

    assert {"home_score", "away_score", "profit_1u", "result", "closing_line_value"}.isdisjoint(filtered)
    assert filtered["game_market_consensus_current_total"] == 8.5


def test_export_service_works_when_db_disabled(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=False)
    manifest = export_service(settings, [prop_row()]).export(date_label="2026-06-22", dry_run=True)

    assert manifest["row_count"] == 1
    assert manifest["leakage_check_passed"] is True


def test_export_service_works_when_game_market_warehouse_unavailable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    row = prop_row()
    for key in list(row):
        if key.startswith("game_market_"):
            row.pop(key)

    result = export_service(settings, [row]).build_features(date_label="2026-06-22", source="edge-board")

    assert result.rows[0]["game_market_available"] is False
    assert result.rows[0]["game_market_enrichment_status"] == "warehouse_unavailable"


def test_export_service_produces_manifest_with_counts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    manifest = export_service(settings, [prop_row(), prop_row(market="pitcher_strikeouts")]).export(
        date_label="2026-06-22",
        dry_run=True,
    )

    assert manifest["row_count"] == 2
    assert manifest["market_counts"] == {"batter_total_bases": 1, "pitcher_strikeouts": 1}
    assert manifest["game_market_match_count"] == 2


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    output_dir = tmp_path / "features"

    manifest = export_service(settings, [prop_row()]).export(
        date_label="2026-06-22",
        dry_run=True,
        output_dir=output_dir,
    )

    assert manifest["dry_run"] is True
    assert not output_dir.exists()


def test_csv_export_writes_expected_columns(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    output_dir = tmp_path / "features"

    export_service(settings, [prop_row(home_score=9)]).export(
        date_label="2026-06-22",
        output_format="csv",
        output_dir=output_dir,
    )

    csv_path = output_dir / "player_prop_features_2026-06-22.csv"
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        row = next(reader)
    assert "game_market_consensus_current_total" in row
    assert "home_score" not in row


def test_json_export_writes_expected_manifest(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    output_dir = tmp_path / "features"

    export_service(settings, [prop_row()]).export(
        date_label="2026-06-22",
        output_format="json",
        output_dir=output_dir,
    )

    manifest = json.loads((output_dir / "ml_feature_export_manifest_2026-06-22.json").read_text(encoding="utf-8"))
    payload = json.loads((output_dir / "player_prop_features_2026-06-22.json").read_text(encoding="utf-8"))
    assert manifest["row_count"] == 1
    assert payload["manifest"]["leakage_check_passed"] is True


def test_preview_endpoint_returns_only_safe_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = export_service(settings, [prop_row(home_score=1, away_score=0, profit_1u=1.0)])
    client = app_with_service(settings, service)

    response = client.get("/api/ml-features/preview?date=2026-06-22&limit=5")

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert {"home_score", "away_score", "profit_1u"}.isdisjoint(row)


def test_admin_export_endpoint_requires_action_header(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = app_with_service(settings, export_service(settings, [prop_row()]))

    denied = client.post("/api/admin/ml-features/export?date=2026-06-22&dryRun=true")
    allowed = client.post(
        "/api/admin/ml-features/export?date=2026-06-22&dryRun=true",
        headers={"X-Baseball-Prop-Action": "1"},
    )

    assert denied.status_code == 403
    assert denied.json()["code"] == "action_header_required"
    assert allowed.status_code == 200
    assert allowed.json()["row_count"] == 1


def test_ml_feature_endpoints_appear_in_openapi(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = app_with_service(settings, export_service(settings, [prop_row()]))
    schema = client.app.openapi()

    assert "/api/admin/ml-features/export" in schema["paths"]
    assert "/api/ml-features/status" in schema["paths"]
    assert "/api/ml-features/backtest-readiness" in schema["paths"]


def test_backtest_readiness_marks_small_or_one_class_markets_not_ready(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    rows = [prop_row(result="win", profit_1u=1.0, propKey=f"row-{index}") for index in range(60)]
    service = BacktestReadinessService(feature_export_service=export_service(settings, rows))

    payload = service.evaluate(date_label="2026-06-22", source="edge-board")

    assert payload["markets"][0]["readiness"] == "not_ready"
    assert payload["markets"][0]["two_class_ready"] is False


def test_backtest_readiness_marks_populated_two_class_market_as_candidate(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    rows = [
        prop_row(
            propKey=f"row-{index}",
            result="win" if index % 2 == 0 else "loss",
            profit_1u=1.0 if index % 2 == 0 else -1.0,
        )
        for index in range(300)
    ]
    service = BacktestReadinessService(feature_export_service=export_service(settings, rows))

    payload = service.evaluate(date_label="2026-06-22", source="edge-board")

    assert payload["markets"][0]["readiness"] == "training_candidate"
    assert payload["markets"][0]["two_class_ready"] is True


def test_data_status_includes_ml_feature_exports(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = app_with_service(settings, export_service(settings, [prop_row()]))

    response = client.get("/api/data/status?season=2026")

    assert response.status_code == 200
    assert "ml_feature_exports" in response.json()


def test_regression_blocked_fields_removed_after_safe_export(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    row = prop_row(
        home_score=7,
        away_score=4,
        profit_1u=1.0,
        result="win",
        closing_line_value=0.25,
    )

    exported = export_service(settings, [row]).build_features(date_label="2026-06-22").rows[0]

    assert {"home_score", "away_score", "profit_1u", "result", "closing_line_value"}.isdisjoint(exported)
    assert filter_safe_features(row).get("profit_1u") is None
