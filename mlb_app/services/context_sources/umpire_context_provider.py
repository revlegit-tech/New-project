from __future__ import annotations

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult, context_path, write_csv_rows


UMPIRE_FIELDS = ["date", "season", "umpire_name", "assignment_status", "ump_k_rate", "ump_zone_size_zscore", "ump_favor_batter_score", "source"]


class UmpireContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "umpire", f"umpire_context_{date_label}.csv")
        write_csv_rows(output_path, [], UMPIRE_FIELDS)
        return ContextProviderResult(
            status="neutral_fallback",
            date=date_label,
            season=season,
            source="umpire",
            rows=0,
            path=str(output_path),
            warnings=["Umpire context unavailable; neutral fallback used."],
            criticalForBoard=False,
        )
