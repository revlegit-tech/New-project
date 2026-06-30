from __future__ import annotations

from pathlib import Path

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult, context_path, read_csv_rows, write_csv_rows


WEATHER_FIELDS = ["date", "season", "game_pk", "team", "opponent", "venue", "temperature", "wind_mph", "source"]


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
        write_csv_rows(output_path, [], WEATHER_FIELDS)
        return ContextProviderResult(status="missing", date=date_label, season=season, source="weather", rows=0, path=str(output_path), warnings=warnings)

    def _candidate_paths(self, date_label: str) -> list[Path]:
        return [
            self.settings.data_dir / "warehouse" / "weather" / f"weather_context_{date_label}.csv",
            self.settings.data_dir / "features" / f"weather_context_{date_label}.csv",
            self.settings.data_dir / "cache" / "weather" / f"weather_context_{date_label}.csv",
        ]
