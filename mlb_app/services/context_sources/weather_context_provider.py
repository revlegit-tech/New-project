from __future__ import annotations

from pathlib import Path

from mlb_app.config import Settings, settings as default_settings
from datetime import datetime, timezone

from mlb_app.services.context_sources.base import ContextProviderResult, context_path, read_csv_rows, schedule_side_rows, write_csv_rows


WEATHER_FIELDS = [
    "date",
    "season",
    "game_pk",
    "team",
    "opponent",
    "venue",
    "temperature",
    "wind_mph",
    "wind_direction",
    "wind_out_score",
    "wind_out_flag",
    "roof_status",
    "turf_flag",
    "cold_game_flag",
    "source",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
]


class WeatherContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "weather", f"weather_context_{date_label}.csv")
        warnings = []
        for source_path in self._candidate_paths(date_label):
            rows = read_csv_rows(source_path)
            if rows:
                write_csv_rows(output_path, rows, sorted({key for row in rows for key in row}))
                return ContextProviderResult(
                    status="partial",
                    date=date_label,
                    season=season,
                    source="weather",
                    rows=len(rows),
                    path=str(output_path),
                    warnings=[f"Weather context copied from local artifact: {source_path}"],
                )
        warnings.append("No local weather context configured; external weather calls skipped.")
        schedule_rows, schedule_source = schedule_side_rows(self.settings, date_label)
        if schedule_rows:
            generated_at = datetime.now(timezone.utc).isoformat()
            fallback_warning = "neutral fallback: schedule and venue known, local weather source unavailable"
            rows = [
                {
                    "date": date_label,
                    "season": season,
                    "game_pk": row.get("game_pk", ""),
                    "team": row.get("team", ""),
                    "opponent": row.get("opponent", ""),
                    "venue": row.get("venue", ""),
                    "temperature": "",
                    "wind_mph": "",
                    "wind_direction": "",
                    "wind_out_score": "",
                    "wind_out_flag": "",
                    "roof_status": "",
                    "turf_flag": "",
                    "cold_game_flag": "",
                    "source": f"neutral_fallback_from_schedule:{schedule_source}",
                    "generatedAt": generated_at,
                    "pregameSafe": True,
                    "labelsExcluded": True,
                    "warnings": fallback_warning,
                }
                for row in schedule_rows
            ]
            warnings.append(fallback_warning)
            write_csv_rows(output_path, rows, WEATHER_FIELDS)
            return ContextProviderResult(
                status="neutral_fallback",
                date=date_label,
                season=season,
                source="weather",
                rows=len(rows),
                path=str(output_path),
                warnings=warnings,
                criticalForBoard=False,
                diagnostics={"fallbackRows": len(rows), "scheduleSource": schedule_source},
            )
        write_csv_rows(output_path, [], WEATHER_FIELDS)
        return ContextProviderResult(status="missing", date=date_label, season=season, source="weather", rows=0, path=str(output_path), warnings=warnings)

    def _candidate_paths(self, date_label: str) -> list[Path]:
        return [
            self.settings.data_dir / "warehouse" / "weather" / f"weather_context_{date_label}.csv",
            self.settings.data_dir / "features" / f"weather_context_{date_label}.csv",
            self.settings.data_dir / "cache" / "weather" / f"weather_context_{date_label}.csv",
        ]
