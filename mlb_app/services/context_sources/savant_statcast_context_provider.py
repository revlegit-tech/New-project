from __future__ import annotations

from pathlib import Path

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult, context_path, read_csv_rows, write_csv_rows


STATCAST_FIELDS = ["date", "season", "player", "pitcher", "barrel_rate", "hard_hit_rate", "xwoba", "xba", "xslg", "source"]


class SavantStatcastContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "statcast", f"statcast_context_{date_label}.csv")
        warnings = []
        for source_path in self._candidate_paths(date_label, season):
            rows = read_csv_rows(source_path)
            if rows:
                write_csv_rows(output_path, rows, sorted({key for row in rows for key in row}))
                return ContextProviderResult(status="partial", date=date_label, season=season, source="statcast", rows=len(rows), path=str(output_path), warnings=[f"Statcast context copied from local artifact: {source_path}"])
        warnings.append("No local Statcast artifact found; external Savant calls skipped.")
        write_csv_rows(output_path, [], STATCAST_FIELDS)
        return ContextProviderResult(status="missing", date=date_label, season=season, source="statcast", rows=0, path=str(output_path), warnings=warnings)

    def _candidate_paths(self, date_label: str, season: int) -> list[Path]:
        return [
            self.settings.data_dir / "features" / f"statcast_context_{date_label}.csv",
            self.settings.data_dir / "warehouse" / "statcast" / f"statcast_{season}.csv",
            self.settings.data_dir / "cache" / "statcast" / f"statcast_{season}.csv",
        ]
