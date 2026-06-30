from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult
from mlb_app.services.context_sources.bullpen_context_provider import BullpenContextProvider
from mlb_app.services.context_sources.game_market_context_provider import GameMarketContextProvider
from mlb_app.services.context_sources.mlb_stats_context_provider import MLBStatsContextProvider
from mlb_app.services.context_sources.odds_movement_context_provider import OddsMovementContextProvider
from mlb_app.services.context_sources.savant_statcast_context_provider import SavantStatcastContextProvider
from mlb_app.services.context_sources.umpire_context_provider import UmpireContextProvider
from mlb_app.services.context_sources.weather_context_provider import WeatherContextProvider


class FeatureSourceAuditService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> dict[str, Any]:
        stats = MLBStatsContextProvider(self.settings)
        results = {
            "player_recent_form": stats.player_recent_form(date_label=date_label, season=season),
            "pitcher_context": stats.pitcher_context(date_label=date_label, season=season),
            "odds_movement": OddsMovementContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "game_markets": GameMarketContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "weather": WeatherContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "statcast": SavantStatcastContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "bullpen_context": BullpenContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "umpire": UmpireContextProvider(self.settings).materialize(date_label=date_label, season=season),
        }
        payload = self._summary(date_label=date_label, season=season, results=results)
        path = self.settings.data_dir / "context" / f"context_source_audit_{date_label}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["path"] = str(path)
        return payload

    def _summary(self, *, date_label: str, season: int, results: dict[str, ContextProviderResult]) -> dict[str, Any]:
        providers = {name: result.to_dict() for name, result in results.items()}
        ready = sorted(name for name, result in results.items() if result.status in {"ok", "partial"} and result.rows > 0)
        missing = sorted(name for name in results if name not in ready)
        warnings = [warning for result in results.values() for warning in result.warnings]
        return {
            "date": date_label,
            "season": int(season),
            "providers": providers,
            "providerStatuses": {name: result.status for name, result in results.items()},
            "rowsByProvider": {name: result.rows for name, result in results.items()},
            "missingFeatureGroups": missing,
            "readyFeatureGroups": ready,
            "warnings": warnings,
            "externalApiCallsMade": sum(result.externalApiCallsMade for result in results.values()),
            "pregameSafe": all(result.pregameSafe for result in results.values()),
            "labelsExcluded": all(result.labelsExcluded for result in results.values()),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
