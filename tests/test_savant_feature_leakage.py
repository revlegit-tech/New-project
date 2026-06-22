from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mlb_app.config import Settings
from mlb_app.repositories.player_metric_repository import PlayerMetricRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.baseball_savant_feature_service import (
    BaseballSavantFeatureService,
    normalize_savant_feature_row,
    safe_batter_statcast_feature_names,
    safe_pitch_type_matchup_feature_names,
    safe_pitcher_analytics_feature_names,
)
from mlb_app.services.feature_store_service import FeatureStoreService
from mlb_app.services.game_environment_feature_service import GameEnvironmentFeatureService


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


def test_savant_schema_supports_requested_feature_groups() -> None:
    batter = set(safe_batter_statcast_feature_names())
    pitcher = set(safe_pitcher_analytics_feature_names())
    pitch_type = set(safe_pitch_type_matchup_feature_names())

    assert {"barrel_rate", "hard_hit_rate", "xwoba", "barrel_rate_l14", "xwoba_vs_lhp"} <= batter
    assert {"k_rate", "projected_pitch_count", "pitch_mix_sweeper", "k_rate_l30"} <= pitcher
    assert {"pitcher_primary_pitch_type", "batter_xwoba_vs_pitcher_primary"} <= pitch_type


def test_savant_leakage_guard_rejects_postgame_fields() -> None:
    with pytest.raises(ValueError):
        normalize_savant_feature_row(
            {
                "date": "2026-06-22",
                "player_name": "Leak Example",
                "barrel_rate": 0.12,
                "home_score": 5,
                "result": "win",
                "profit_1u": 1.0,
            },
            dataset="statcast_batter_daily",
        )


def test_player_metric_repository_writes_and_reads_csv_fallback(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    db = WarehouseDatabase.from_settings(settings)
    repository = PlayerMetricRepository(db, settings=settings)
    service = BaseballSavantFeatureService(repository)

    result = service.upsert_rows(
        "statcast_batter_daily",
        [
            {
                "date": "2026-06-22",
                "season": 2026,
                "player_id": "592450",
                "player_name": "Aaron Judge",
                "team": "NYY",
                "opponent": "BAL",
                "barrel_rate": 0.19,
                "xwoba_l14": 0.441,
            }
        ],
        date_label="2026-06-22",
    )
    rows = repository.read_rows("statcast_batter_daily", date_label="2026-06-22", player_id="592450")

    assert result.mode == "csv"
    assert rows[0]["player_name"] == "Aaron Judge"
    assert rows[0]["barrel_rate"] == "0.19"


def test_feature_service_joins_batter_pitcher_pitch_type_and_environment() -> None:
    service = FeatureStoreService(
        savant_feature_service=BaseballSavantFeatureService(),
        game_environment_feature_service=GameEnvironmentFeatureService(),
    )

    row = service.build_feature_row(
        date_label="2026-06-22",
        batter_row={
            "date": "2026-06-22",
            "season": 2026,
            "player_id": "592450",
            "player_name": "Aaron Judge",
            "team": "NYY",
            "opponent": "BAL",
            "barrel_rate": 0.18,
            "hard_hit_rate_l7": 0.54,
        },
        pitcher_row={
            "date": "2026-06-22",
            "player_id": "999999",
            "player_name": "Test Starter",
            "team": "BAL",
            "opponent": "NYY",
            "k_rate": 0.31,
            "projected_pitch_count": 92,
        },
        pitch_type_row={
            "date": "2026-06-22",
            "player_id": "592450",
            "player_name": "Aaron Judge",
            "pitcher_primary_pitch_type": "FF",
            "batter_xwoba_vs_pitcher_primary": 0.402,
        },
        environment_row={
            "date": "2026-06-22",
            "game_id": "game-1",
            "park": "Yankee Stadium",
            "park_factor_runs": 1.04,
            "wind_out_to_cf": 0.2,
            "roof_status": "open",
        },
    )

    assert row["batter_barrel_rate"] == 0.18
    assert row["batter_hard_hit_rate_l7"] == 0.54
    assert row["pitcher_k_rate"] == 0.31
    assert row["pitcher_projected_pitch_count"] == 92
    assert row["pitcher_primary_pitch_type"] == "FF"
    assert row["park_factor_runs"] == 1.04
    assert {"home_score", "away_score", "result", "profit_1u"}.isdisjoint(row)
