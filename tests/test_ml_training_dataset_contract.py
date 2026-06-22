from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.ml.datasets.feature_matrix_builder import build_feature_matrix
from mlb_app.ml.datasets.target_builder import build_binary_target
from mlb_app.services.backtest_dataset_builder_service import BacktestDatasetBuilderService


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


def feature_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "feature_schema_version": "ml-player-prop-features.sprint13c.v1",
        "exported_at": "2026-06-22T12:00:00+00:00",
        "source": "edge-board",
        "source_row_id": "row-1",
        "prop_key": "row-1",
        "date": "2026-06-22",
        "season": 2026,
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_total_bases",
        "side": "Over",
        "line": "1.5",
        "book": "ExampleBook",
        "american_odds": "-110",
        "implied_probability_percent": "52.38",
        "model_probability_percent": "57.5",
        "game_market_available": True,
        "game_market_game_id": "game-1",
        "game_market_team_no_vig_win_prob_current": "0.61",
        "game_market_opponent_no_vig_win_prob_current": "0.39",
        "game_market_enrichment_status": "matched",
    }
    row.update(overrides)
    return row


def label_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "label_schema_version": "player-prop-labels.sprint13d.v1",
        "graded_at": "2026-06-23T00:00:00+00:00",
        "date": "2026-06-22",
        "season": 2026,
        "source_row_id": "row-1",
        "prop_key": "row-1",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_total_bases",
        "side": "Over",
        "line": "1.5",
        "actual_value": 2,
        "result": "win",
        "hit": True,
        "push": False,
        "void": False,
        "label_status": "graded",
        "label_reason": "synthetic",
        "stat_source": "test",
        "stat_key": "totalBases",
    }
    row.update(overrides)
    return row


def write_training_inputs(settings: Settings, features: list[dict[str, Any]], labels: list[dict[str, Any]]) -> None:
    feature_path = settings.data_dir / "warehouse" / "ml_features" / "player_prop_features_2026-06-22.json"
    label_path = settings.data_dir / "warehouse" / "ml_labels" / "player_prop_labels_2026-06-22.json"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.write_text(json.dumps({"rows": features}), encoding="utf-8")
    label_path.write_text(json.dumps({"rows": labels}), encoding="utf-8")


def test_training_dataset_builder_emits_only_prefixed_columns(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_training_inputs(settings, [feature_row()], [label_row()])
    service = BacktestDatasetBuilderService(settings=settings)

    result = service.build_training_rows(date_label="2026-06-22", include_ungraded=True)
    row = result.rows[0]

    assert all(key.startswith(("feature_", "target_", "meta_")) for key in row)
    assert row["feature_line"] == "1.5"
    assert row["target_actual_value"] == 2
    assert row["target_result"] == "win"
    assert row["meta_player"] == "Aaron Judge"
    assert {"line", "player", "result", "actual_value", "graded_at"}.isdisjoint(row)
    assert result.manifest["feature_columns"][0].startswith("feature_")
    assert result.manifest["metadata_columns"][0].startswith("meta_")


def test_training_preview_separates_features_targets_and_metadata(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_training_inputs(settings, [feature_row()], [label_row()])
    service = BacktestDatasetBuilderService(settings=settings)

    preview = service.preview(date_label="2026-06-22", limit=1)
    preview_row = preview["rows"][0]

    assert set(preview_row) == {"features", "targets", "metadata"}
    assert "feature_line" in preview_row["features"]
    assert "target_hit" in preview_row["targets"]
    assert "meta_player" in preview_row["metadata"]


def test_metadata_is_preserved_but_not_sent_to_model_matrix(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_training_inputs(settings, [feature_row()], [label_row()])
    service = BacktestDatasetBuilderService(settings=settings)
    rows = service.build_training_rows(date_label="2026-06-22", include_ungraded=True).rows

    matrix = build_feature_matrix(rows)
    target = build_binary_target(rows)

    assert "meta_player" in rows[0]
    assert all(column.startswith("feature_") for column in matrix.columns)
    assert not any(column.startswith(("meta_", "target_")) for column in matrix.columns)
    assert target.tolist() == [1]


def test_training_builder_rejects_leaky_feature_rows(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_training_inputs(
        settings,
        [feature_row(result="win", actual_value=2, profit_1u=1.0)],
        [label_row()],
    )
    service = BacktestDatasetBuilderService(settings=settings)

    result = service.build_training_rows(date_label="2026-06-22", include_ungraded=True)

    assert result.rows == []
    assert result.manifest["leakage_check_passed"] is False
    assert {"result", "actual_value", "profit_1u"} & set(result.manifest["blocked_feature_fields_found"])


def test_csv_fallback_writes_training_artifacts_under_temp_data_dir(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'warehouse.sqlite3').as_posix()}"
    settings = make_settings(tmp_path, db_enabled=True, db_fallback_to_csv=True, database_url=database_url)
    write_training_inputs(settings, [feature_row()], [label_row()])
    service = BacktestDatasetBuilderService(settings=settings)

    manifest = service.build_training_dataset(date_label="2026-06-22", include_ungraded=True, output_format="csv")
    csv_path = settings.data_dir / "warehouse" / "ml_training" / "player_prop_training_2026-06-22.csv"

    assert manifest["written"] is True
    assert csv_path.exists()
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        fields = list(csv.DictReader(handle).fieldnames or [])
    assert fields
    assert all(field.startswith(("feature_", "target_", "meta_")) for field in fields)
