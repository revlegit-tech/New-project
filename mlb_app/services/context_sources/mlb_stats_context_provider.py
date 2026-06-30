from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import (
    ContextProviderResult,
    clean,
    context_path,
    first_value,
    key,
    read_csv_rows,
    status_for_rows,
    to_float,
    write_csv_rows,
)


PLAYER_RECENT_FORM_FIELDS = [
    "date",
    "season",
    "player",
    "team",
    "recent_games",
    "recent_rate",
    "season_rate",
    "rolling_avg_5",
    "rolling_avg_10",
    "rolling_avg_15",
    "rolling_total_bases_10",
    "rolling_hr_rate_15",
    "rolling_k_rate_10",
    "source",
]

PITCHER_CONTEXT_FIELDS = [
    "date",
    "season",
    "pitcher",
    "team",
    "pitcher_recent_games",
    "pitcher_k_rate",
    "pitcher_walk_rate",
    "pitcher_hr_rate",
    "pitcher_babip",
    "pitcher_days_rest",
    "pitcher_velo_delta",
    "source",
]


class MLBStatsContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def player_recent_form(self, *, date_label: str, season: int) -> ContextProviderResult:
        path = context_path(self.settings, "player_recent_form", f"player_recent_form_{date_label}.csv")
        source = self._batter_log_path(season)
        warnings: list[str] = []
        if not source.is_file():
            warnings.append("Local batter game log not found.")
            write_csv_rows(path, [], PLAYER_RECENT_FORM_FIELDS)
            return self._result("missing", date_label, season, "player_recent_form", 0, path, warnings)

        rows = _pregame_rows(read_csv_rows(source), date_label)
        if rows and (
            not _has_any_column(rows, ["strikeOuts", "strikeouts", "k"])
            or not _has_any_column(rows, ["plateAppearances", "pa"])
        ):
            warnings.append("rolling_k_rate_10 unavailable from local batter logs; field left null where unsafe.")
        output = [_batter_summary(date_label, season, player_rows, source) for player_rows in _group_player_rows(rows)]
        if not output:
            warnings.append("No prior batter game logs available before target date.")
        write_csv_rows(path, output, PLAYER_RECENT_FORM_FIELDS)
        return self._result(status_for_rows(len(output), warnings), date_label, season, "player_recent_form", len(output), path, warnings)

    def pitcher_context(self, *, date_label: str, season: int) -> ContextProviderResult:
        path = context_path(self.settings, "pitcher_context", f"pitcher_context_{date_label}.csv")
        source = self._pitcher_log_path(season)
        warnings: list[str] = []
        if not source.is_file():
            warnings.append("Local pitcher game log not found.")
            write_csv_rows(path, [], PITCHER_CONTEXT_FIELDS)
            return self._result("missing", date_label, season, "pitcher_context", 0, path, warnings)

        rows = _pregame_rows(read_csv_rows(source), date_label)
        if rows and not _has_any_column(rows, ["battersFaced", "batters_faced", "bf"]):
            warnings.append("Pitcher rate denominators unavailable from local pitcher logs; rate fields left null where unsafe.")
        if rows and not _has_any_column(rows, ["releaseSpeed", "release_speed", "avgFastballVelo", "fastballVelo"]):
            warnings.append("pitcher_velo_delta unavailable from local pitcher logs; field left null.")
        output = [_pitcher_summary(date_label, season, pitcher_rows, source) for pitcher_rows in _group_pitcher_rows(rows)]
        if not output:
            warnings.append("No prior pitcher game logs available before target date.")
        write_csv_rows(path, output, PITCHER_CONTEXT_FIELDS)
        return self._result(status_for_rows(len(output), warnings), date_label, season, "pitcher_context", len(output), path, warnings)

    def _batter_log_path(self, season: int) -> Path:
        return self.settings.data_dir / "cloud" / "season_logs" / f"batter_game_logs_{season}.csv"

    def _pitcher_log_path(self, season: int) -> Path:
        return self.settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv"

    def _result(
        self,
        status: str,
        date_label: str,
        season: int,
        source: str,
        rows: int,
        path: Path,
        warnings: list[str],
    ) -> ContextProviderResult:
        return ContextProviderResult(
            status=status,
            date=date_label,
            season=season,
            source=source,
            rows=rows,
            path=str(path),
            warnings=warnings,
        )


def _pregame_rows(rows: list[dict[str, str]], date_label: str) -> list[dict[str, str]]:
    try:
        target = date.fromisoformat(date_label)
    except ValueError:
        return []
    prior: list[dict[str, str]] = []
    for row in rows:
        raw = clean(first_value(row, ["date", "game_date", "gameDate"]))
        try:
            row_date = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if row_date < target:
            prior.append(row)
    return prior


def _group_player_rows(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        player = clean(first_value(row, ["player", "playerName", "name"]))
        if not player:
            continue
        grouped.setdefault((key(player), clean(first_value(row, ["team", "teamAbbr"]))), []).append(row)
    return [_sort_rows(value) for value in grouped.values()]


def _group_pitcher_rows(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    return _group_player_rows(rows)


def _sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: clean(first_value(row, ["date", "game_date", "gameDate"])))


def _batter_summary(date_label: str, season: int, rows: list[dict[str, str]], source: Path) -> dict[str, Any]:
    player = clean(first_value(rows[-1], ["player", "playerName", "name"]))
    team = clean(first_value(rows[-1], ["team", "teamAbbr"]))
    at_bats = sum(to_float(first_value(row, ["atBats", "at_bats", "ab"])) for row in rows)
    hits = sum(to_float(first_value(row, ["hits", "h"])) for row in rows)
    strikeouts_10 = sum(to_float(first_value(row, ["strikeOuts", "strikeouts", "k"])) for row in rows[-10:])
    pa_10 = sum(to_float(first_value(row, ["plateAppearances", "pa"])) for row in rows[-10:])
    return {
        "date": date_label,
        "season": season,
        "player": player,
        "team": team,
        "recent_games": len(rows),
        "recent_rate": _rate(sum(to_float(first_value(row, ["hits", "h"])) for row in rows[-10:]), len(rows[-10:])),
        "season_rate": _rate(hits, at_bats),
        "rolling_avg_5": _rate(sum(to_float(first_value(row, ["hits", "h"])) for row in rows[-5:]), len(rows[-5:])),
        "rolling_avg_10": _rate(sum(to_float(first_value(row, ["hits", "h"])) for row in rows[-10:]), len(rows[-10:])),
        "rolling_avg_15": _rate(sum(to_float(first_value(row, ["hits", "h"])) for row in rows[-15:]), len(rows[-15:])),
        "rolling_total_bases_10": round(sum(to_float(first_value(row, ["totalBases", "total_bases", "tb"])) for row in rows[-10:]), 4),
        "rolling_hr_rate_15": _rate(sum(to_float(first_value(row, ["homeRuns", "home_runs", "hr"])) for row in rows[-15:]), len(rows[-15:])),
        "rolling_k_rate_10": _rate(strikeouts_10, pa_10),
        "source": str(source),
    }


def _pitcher_summary(date_label: str, season: int, rows: list[dict[str, str]], source: Path) -> dict[str, Any]:
    pitcher = clean(first_value(rows[-1], ["player", "pitcher", "playerName", "name"]))
    team = clean(first_value(rows[-1], ["team", "teamAbbr"]))
    batters = sum(to_float(first_value(row, ["battersFaced", "batters_faced", "bf"])) for row in rows)
    strikeouts = sum(to_float(first_value(row, ["strikeOuts", "strikeouts", "k"])) for row in rows)
    walks = sum(to_float(first_value(row, ["baseOnBalls", "walks", "bb"])) for row in rows)
    homers = sum(to_float(first_value(row, ["homeRuns", "home_runs", "hr"])) for row in rows)
    hits = sum(to_float(first_value(row, ["hits", "h"])) for row in rows)
    balls_in_play = batters - strikeouts - walks - homers
    days_rest = ""
    try:
        days_rest = (date.fromisoformat(date_label) - date.fromisoformat(clean(rows[-1].get("date"))[:10])).days
    except ValueError:
        days_rest = ""
    return {
        "date": date_label,
        "season": season,
        "pitcher": pitcher,
        "team": team,
        "pitcher_recent_games": len(rows),
        "pitcher_k_rate": _rate(strikeouts, batters),
        "pitcher_walk_rate": _rate(walks, batters),
        "pitcher_hr_rate": _rate(homers, batters),
        "pitcher_babip": _rate(hits - homers, balls_in_play),
        "pitcher_days_rest": days_rest,
        "pitcher_velo_delta": "",
        "source": str(source),
    }


def _rate(numerator: float, denominator: float) -> float | str:
    if denominator <= 0:
        return ""
    return round(numerator / denominator, 6)


def _has_any_column(rows: list[dict[str, str]], aliases: list[str]) -> bool:
    return any(any(clean(row.get(alias)) for alias in aliases) for row in rows)
