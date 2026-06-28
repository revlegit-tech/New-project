from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.ml_feature_export_service import MLFeatureExportService
from mlb_app.services.player_prop_label_builder_service import PlayerPropLabelBuilderService


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


class FixtureFeatureExportService(MLFeatureExportService):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def build_features(self, *args: Any, **kwargs: Any) -> Any:
        return type("Build", (), {"rows": self.rows, "manifest": {"warnings": []}})()


def test_player_prop_labels_use_real_market_and_sprint31_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    log_path = settings.data_dir / "warehouse" / "season_logs" / "batter_game_logs_2026.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("date,player,team,hits,totalBases\n2026-06-24,Aaron Judge,NYY,2,4\n", encoding="utf-8")
    service = PlayerPropLabelBuilderService(
        settings=settings,
        feature_export_service=FixtureFeatureExportService(
            [
                {
                    "date": "2026-06-24",
                    "season": 2026,
                    "game_pk": "777",
                    "player_id": "123",
                    "prop_key": "p1",
                    "player": "Aaron Judge",
                    "team": "NYY",
                    "opponent": "BAL",
                    "market": "batter_hits",
                    "side": "Over",
                    "line": "1.5",
                    "rawSource": "fixture.csv",
                }
            ]
        ),
    )

    result = service.build_label_rows(date_label="2026-06-24", season=2026, graded_at=datetime(2026, 6, 25, tzinfo=timezone.utc))
    row = result.rows[0]

    assert row["market"] == "batter_hits"
    assert row["market"] != "unknown"
    assert row["result"] == "hit"
    assert row["hit"] is True
    assert row["game_pk"] == "777"
    assert row["player_id"] == "123"
    assert "source_file" in row
    assert "label_quality_flags" in row
