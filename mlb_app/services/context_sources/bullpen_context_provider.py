from __future__ import annotations

from datetime import date, datetime, timezone

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult, context_path, first_value, read_csv_rows, schedule_side_rows, to_float, write_csv_rows


BULLPEN_FIELDS = [
    "date",
    "season",
    "team",
    "opponent",
    "opponent_bullpen_era_7d",
    "bullpen_recent_usage_score",
    "bullpen_games_last_3d",
    "bullpen_innings_last_3d",
    "bullpen_rest_warning",
    "source",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
]


class BullpenContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "bullpen", f"bullpen_context_{date_label}.csv")
        source_path = self.settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        warnings = []
        schedule_rows, schedule_source = schedule_side_rows(self.settings, date_label)
        generated_at = datetime.now(timezone.utc).isoformat()
        if not source_path.is_file():
            warnings.append("Local pitcher game log not found; bullpen split unavailable.")
            rows = _fallback_rows(date_label, season, schedule_rows, schedule_source, generated_at, warnings[-1])
            write_csv_rows(output_path, rows, BULLPEN_FIELDS)
            return ContextProviderResult(
                status="neutral_fallback" if rows else "missing",
                date=date_label,
                season=season,
                source="bullpen_context",
                rows=len(rows),
                path=str(output_path),
                warnings=warnings,
                criticalForBoard=False,
                diagnostics={"fallbackRows": len(rows), "scheduleSource": schedule_source},
            )
        by_team: dict[str, dict[str, float]] = {}
        for row in read_csv_rows(source_path):
            row_date = str(row.get("date") or "")[:10]
            if not row_date or row_date >= date_label:
                continue
            team = str(first_value(row, ["team", "teamAbbr"])).strip()
            if not team:
                continue
            bucket = by_team.setdefault(team, {"er": 0.0, "ip": 0.0, "ip_3d": 0.0, "games_3d": 0.0})
            bucket["er"] += to_float(first_value(row, ["earnedRuns", "earned_runs", "er"]))
            innings = to_float(first_value(row, ["inningsPitched", "innings_pitched", "ip"]))
            bucket["ip"] += innings
            if _days_between(row_date, date_label) <= 3:
                bucket["ip_3d"] += innings
                bucket["games_3d"] += 1
        if schedule_rows:
            rows = []
            for side in schedule_rows:
                opponent = str(side.get("opponent", ""))
                values = by_team.get(opponent, {"er": 0.0, "ip": 0.0, "ip_3d": 0.0, "games_3d": 0.0})
                innings_3d = values["ip_3d"]
                opponent_history_available = opponent in by_team
                rest_warning = "neutral fallback" if not opponent_history_available else "high recent bullpen usage" if innings_3d >= 10 else ""
                rows.append(
                    {
                        "date": date_label,
                        "season": season,
                        "team": side.get("team", ""),
                        "opponent": opponent,
                        "opponent_bullpen_era_7d": "" if values["ip"] <= 0 else round((values["er"] * 9.0) / values["ip"], 6),
                        "bullpen_recent_usage_score": "" if not opponent_history_available else round(min(1.0, innings_3d / 12.0), 6),
                        "bullpen_games_last_3d": "" if not opponent_history_available else int(values["games_3d"]),
                        "bullpen_innings_last_3d": "" if not opponent_history_available else round(innings_3d, 6),
                        "bullpen_rest_warning": rest_warning,
                        "source": str(source_path) if opponent_history_available else f"neutral_fallback_from_schedule:{schedule_source}" if schedule_source else "neutral_fallback",
                        "generatedAt": generated_at,
                        "pregameSafe": True,
                        "labelsExcluded": True,
                        "warnings": "uses prior local pitcher logs only; role-specific bullpen split unavailable"
                        if opponent_history_available
                        else "no prior pitcher logs for scheduled opponent; neutral fallback",
                    }
                )
        else:
            rows = [{
                "date": date_label,
                "season": season,
                "team": team,
                "opponent": "",
                "opponent_bullpen_era_7d": "" if values["ip"] <= 0 else round((values["er"] * 9.0) / values["ip"], 6),
                "bullpen_recent_usage_score": round(min(1.0, values["ip_3d"] / 12.0), 6),
                "bullpen_games_last_3d": int(values["games_3d"]),
                "bullpen_innings_last_3d": round(values["ip_3d"], 6),
                "bullpen_rest_warning": "high recent bullpen usage" if values["ip_3d"] >= 10 else "",
                "source": str(source_path),
                "generatedAt": generated_at,
                "pregameSafe": True,
                "labelsExcluded": True,
                "warnings": "uses prior local pitcher logs only; schedule unavailable for opponent join",
            } for team, values in sorted(by_team.items())]
        fallback_rows = sum(1 for row in rows if "fallback" in str(row.get("source") or row.get("warnings") or "").lower())
        if rows and fallback_rows == len(rows):
            warnings.append("No prior pitcher logs available for scheduled opponents; neutral fallback used.")
        elif rows:
            warnings.append("Bullpen context uses team-level local pitcher logs where available; unmatched opponents use neutral fallback.")
        else:
            warnings.append("No prior pitcher logs available before target date.")
        write_csv_rows(output_path, rows, BULLPEN_FIELDS)
        status = "neutral_fallback" if rows and fallback_rows == len(rows) else "partial" if rows else "missing"
        return ContextProviderResult(
            status=status,
            date=date_label,
            season=season,
            source="bullpen_context",
            rows=len(rows),
            path=str(output_path),
            warnings=warnings,
            criticalForBoard=False if fallback_rows else True,
            diagnostics={"fallbackRows": fallback_rows, "scheduleSource": schedule_source},
        )


def _fallback_rows(date_label: str, season: int, schedule_rows: list[dict[str, str]], schedule_source: str, generated_at: str, warning: str) -> list[dict[str, object]]:
    fallback_warning = f"{warning}; neutral fallback"
    return [
        {
            "date": date_label,
            "season": season,
            "team": row.get("team", ""),
            "opponent": row.get("opponent", ""),
            "opponent_bullpen_era_7d": "",
            "bullpen_recent_usage_score": "",
            "bullpen_games_last_3d": "",
            "bullpen_innings_last_3d": "",
            "bullpen_rest_warning": "neutral fallback",
            "source": f"neutral_fallback_from_schedule:{schedule_source}" if schedule_source else "neutral_fallback",
            "generatedAt": generated_at,
            "pregameSafe": True,
            "labelsExcluded": True,
            "warnings": fallback_warning,
        }
        for row in schedule_rows
    ]


def _days_between(row_date: str, date_label: str) -> int:
    try:
        return (date.fromisoformat(date_label) - date.fromisoformat(row_date)).days
    except ValueError:
        return 999
