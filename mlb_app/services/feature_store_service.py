from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mlb_app.services.baseball_savant_feature_service import BaseballSavantFeatureService, assert_no_savant_leakage_fields
from mlb_app.services.game_environment_feature_service import GameEnvironmentFeatureService


class FeatureStoreService:
    """Facade for building safe player-prop feature rows from warehouse slices."""

    def __init__(
        self,
        *,
        savant_feature_service: BaseballSavantFeatureService,
        game_environment_feature_service: GameEnvironmentFeatureService,
    ) -> None:
        self.savant_feature_service = savant_feature_service
        self.game_environment_feature_service = game_environment_feature_service

    def build_feature_row(
        self,
        *,
        batter_row: Mapping[str, Any] | None = None,
        pitcher_row: Mapping[str, Any] | None = None,
        pitch_type_row: Mapping[str, Any] | None = None,
        environment_row: Mapping[str, Any] | None = None,
        date_label: str = "",
    ) -> dict[str, Any]:
        row = self.savant_feature_service.build_matchup_feature_row(
            batter_row=batter_row,
            pitcher_row=pitcher_row,
            pitch_type_row=pitch_type_row,
            environment_row=environment_row,
            date_label=date_label,
        )
        assert_no_savant_leakage_fields(row)
        return row

    def empty_feature_result(self, *, date_label: str = "") -> dict[str, Any]:
        return {
            "status": "ok",
            "date": date_label,
            "rows": [],
            "warnings": [],
        }
