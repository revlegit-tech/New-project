from __future__ import annotations

from datetime import datetime, timezone

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult, context_path, schedule_side_rows, write_csv_rows


UMPIRE_FIELDS = [
    "date",
    "season",
    "game_id",
    "event_id",
    "game_pk",
    "home_team",
    "away_team",
    "umpire_name",
    "assignment_status",
    "ump_k_rate",
    "ump_zone_size_zscore",
    "ump_favor_batter_score",
    "source",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
]


class UmpireContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "umpire", f"umpire_context_{date_label}.csv")
        schedule_rows, schedule_source = schedule_side_rows(self.settings, date_label)
        generated_at = datetime.now(timezone.utc).isoformat()
        fallback_warning = "neutral fallback: confirmed umpire assignments unavailable"
        games: dict[tuple[str, str, str], dict[str, str]] = {}
        for row in schedule_rows:
            key = (str(row.get("game_pk", "")), str(row.get("home_team", "")), str(row.get("away_team", "")))
            games.setdefault(key, row)
        rows = [
            {
                "date": date_label,
                "season": season,
                "game_id": row.get("game_pk", ""),
                "event_id": row.get("game_pk", ""),
                "game_pk": row.get("game_pk", ""),
                "home_team": row.get("home_team", ""),
                "away_team": row.get("away_team", ""),
                "umpire_name": "",
                "assignment_status": "neutral_fallback",
                "ump_k_rate": "",
                "ump_zone_size_zscore": "",
                "ump_favor_batter_score": "",
                "source": f"neutral_fallback_from_schedule:{schedule_source}" if schedule_source else "neutral_fallback",
                "generatedAt": generated_at,
                "pregameSafe": True,
                "labelsExcluded": True,
                "warnings": fallback_warning,
            }
            for row in games.values()
        ]
        write_csv_rows(output_path, rows, UMPIRE_FIELDS)
        return ContextProviderResult(
            status="neutral_fallback",
            date=date_label,
            season=season,
            source="umpire",
            rows=len(rows),
            path=str(output_path),
            warnings=["Umpire context unavailable; neutral fallback used."],
            criticalForBoard=False,
            diagnostics={"fallbackRows": len(rows), "scheduleSource": schedule_source},
        )
