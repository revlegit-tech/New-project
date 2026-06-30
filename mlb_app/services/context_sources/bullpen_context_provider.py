from __future__ import annotations

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult, context_path, first_value, read_csv_rows, to_float, write_csv_rows


BULLPEN_FIELDS = ["date", "season", "team", "opponent_bullpen_era_7d", "source"]


class BullpenContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "bullpen", f"bullpen_context_{date_label}.csv")
        source_path = self.settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        warnings = []
        if not source_path.is_file():
            warnings.append("Local pitcher game log not found; bullpen split unavailable.")
            write_csv_rows(output_path, [], BULLPEN_FIELDS)
            return ContextProviderResult(status="missing", date=date_label, season=season, source="bullpen_context", rows=0, path=str(output_path), warnings=warnings)
        by_team: dict[str, dict[str, float]] = {}
        for row in read_csv_rows(source_path):
            row_date = str(row.get("date") or "")[:10]
            if not row_date or row_date >= date_label:
                continue
            team = str(first_value(row, ["team", "teamAbbr"])).strip()
            if not team:
                continue
            bucket = by_team.setdefault(team, {"er": 0.0, "ip": 0.0})
            bucket["er"] += to_float(first_value(row, ["earnedRuns", "earned_runs", "er"]))
            bucket["ip"] += to_float(first_value(row, ["inningsPitched", "innings_pitched", "ip"]))
        rows = [
            {
                "date": date_label,
                "season": season,
                "team": team,
                "opponent_bullpen_era_7d": "" if values["ip"] <= 0 else round((values["er"] * 9.0) / values["ip"], 6),
                "source": str(source_path),
            }
            for team, values in sorted(by_team.items())
        ]
        if rows:
            warnings.append("Bullpen context uses team-level local pitcher logs; no role-specific bullpen split available.")
        else:
            warnings.append("No prior pitcher logs available before target date.")
        write_csv_rows(output_path, rows, BULLPEN_FIELDS)
        return ContextProviderResult(status="partial" if rows else "missing", date=date_label, season=season, source="bullpen_context", rows=len(rows), path=str(output_path), warnings=warnings)
