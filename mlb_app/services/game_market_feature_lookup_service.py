from __future__ import annotations

from typing import Any

from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.warehouse_utils import clean
from mlb_app.services.historical_game_odds_import_service import normalize_team


class GameMarketFeatureLookupService:
    """Safe read interface for Sprint 13B playerboard enrichment."""

    def __init__(self, repository: HistoricalGameOddsRepository | None) -> None:
        self.repository = repository

    def feature_for_matchup(self, *, date: str, team: str, opponent: str) -> dict[str, Any]:
        if self.repository is None:
            return {}
        try:
            row = self.repository.feature_by_matchup(
                date_label=clean(date),
                team=normalize_team(team),
                opponent=normalize_team(opponent),
            )
        except Exception:
            return {}
        return dict(row or {})
