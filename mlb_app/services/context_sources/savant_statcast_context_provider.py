from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
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


STATCAST_FIELDS = [
    "date",
    "season",
    "player",
    "pitcher",
    "team",
    "barrel_rate",
    "hard_hit_rate",
    "xwoba",
    "xba",
    "xslg",
    "batter_babip",
    "batter_k_rate",
    "batter_walk_rate",
    "batter_ld_rate",
    "batter_gb_rate",
    "batter_sprint_speed",
    "source",
    "sourceUpdatedAt",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
]


class SavantStatcastContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "statcast", f"statcast_context_{date_label}.csv")
        warnings = []
        for source_path in self._candidate_paths(date_label, season):
            rows = read_csv_rows(source_path)
            pregame_rows = _pregame_rows(rows, date_label)
            if not pregame_rows:
                continue
            generated_at = datetime.now(timezone.utc).isoformat()
            output = [
                _statcast_summary(date_label, season, player_rows, source_path, generated_at)
                for player_rows in _group_batter_rows(pregame_rows)
            ]
            output = [row for row in output if row.get("player")]
            if not output:
                warnings.append(f"Local Statcast artifact contained no safely identifiable batter rows: {source_path}")
                continue
            if not _has_any_column(pregame_rows, ["launch_speed"]):
                warnings.append("hard_hit_rate unavailable; local Statcast launch_speed missing.")
            if not _has_any_column(pregame_rows, ["estimated_woba_using_speedangle"]):
                warnings.append("xwoba unavailable; local Statcast expected wOBA missing.")
            if not _has_any_column(pregame_rows, ["estimated_ba_using_speedangle"]):
                warnings.append("xba unavailable; local Statcast expected BA missing.")
            if not _has_any_column(pregame_rows, ["estimated_slg_using_speedangle"]):
                warnings.append("xslg unavailable; local Statcast expected SLG missing.")
            warnings.append(f"Statcast context derived from local artifact: {source_path}")
            write_csv_rows(output_path, output, STATCAST_FIELDS)
            return ContextProviderResult(
                status=status_for_rows(len(output), warnings),
                date=date_label,
                season=season,
                source="statcast",
                rows=len(output),
                path=str(output_path),
                warnings=warnings,
            )
        warnings.append("No local Statcast artifact found; external Savant calls skipped.")
        write_csv_rows(output_path, [], STATCAST_FIELDS)
        return ContextProviderResult(status="missing", date=date_label, season=season, source="statcast", rows=0, path=str(output_path), warnings=warnings)

    def _candidate_paths(self, date_label: str, season: int) -> list[Path]:
        return [
            self.settings.data_dir / "features" / f"statcast_context_{date_label}.csv",
            self.settings.data_dir / "warehouse" / "statcast" / f"statcast_{season}.csv",
            self.settings.data_dir / "cache" / "statcast" / f"statcast_{season}.csv",
            *sorted((self.settings.data_dir / "cache" / "savant" / "raw").glob(f"statcast_{season}_*.csv")),
        ]


def _pregame_rows(rows: list[dict[str, str]], date_label: str) -> list[dict[str, str]]:
    try:
        target = date.fromisoformat(date_label)
    except ValueError:
        return []
    output: list[dict[str, str]] = []
    for row in rows:
        raw = clean(first_value(row, ["date", "game_date", "gameDate"]))
        try:
            row_date = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if row_date < target:
            output.append(row)
    return output


def _group_batter_rows(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        player = _normal_name(clean(first_value(row, ["player", "batter_name", "batterName", "name"])))
        if not player:
            continue
        team = clean(first_value(row, ["team", "bat_team", "batTeam", "away_team", "home_team"]))
        grouped[(key(player), team)].append(row)
    return list(grouped.values())


def _statcast_summary(date_label: str, season: int, rows: list[dict[str, str]], source: Path, generated_at: str) -> dict[str, Any]:
    latest = rows[-1]
    player = _normal_name(clean(first_value(latest, ["player", "batter_name", "batterName", "name"])))
    batted_ball_rows = [row for row in rows if clean(first_value(row, ["launch_speed", "launchSpeed"]))]
    pa_rows = _plate_appearance_rows(rows)
    at_bats = [row for row in pa_rows if _event(row) not in {"walk", "hit_by_pitch", "sac_bunt", "sac_fly", "catcher_interf"}]
    hits = [row for row in at_bats if _event(row) in {"single", "double", "triple", "home_run"}]
    homers = [row for row in at_bats if _event(row) == "home_run"]
    strikeouts = [row for row in pa_rows if _event(row) == "strikeout"]
    walks = [row for row in pa_rows if _event(row) == "walk"]
    balls_in_play = [row for row in at_bats if _event(row) not in {"strikeout", "home_run"}]
    return {
        "date": date_label,
        "season": season,
        "player": player,
        "pitcher": "",
        "team": clean(first_value(latest, ["team", "bat_team", "batTeam", "away_team", "home_team"])),
        "barrel_rate": _rate(sum(1 for row in batted_ball_rows if clean(first_value(row, ["launch_speed_angle"])) == "6"), len(batted_ball_rows)),
        "hard_hit_rate": _rate(sum(1 for row in batted_ball_rows if to_float(first_value(row, ["launch_speed"]), -1) >= 95), len(batted_ball_rows)),
        "xwoba": _avg(rows, ["estimated_woba_using_speedangle", "xwoba"]),
        "xba": _avg(rows, ["estimated_ba_using_speedangle", "xba"]),
        "xslg": _avg(rows, ["estimated_slg_using_speedangle", "xslg"]),
        "batter_babip": _rate(len(hits) - len(homers), len(balls_in_play)),
        "batter_k_rate": _rate(len(strikeouts), len(pa_rows)),
        "batter_walk_rate": _rate(len(walks), len(pa_rows)),
        "batter_ld_rate": _rate(sum(1 for row in batted_ball_rows if clean(first_value(row, ["bb_type"])) == "line_drive"), len(batted_ball_rows)),
        "batter_gb_rate": _rate(sum(1 for row in batted_ball_rows if clean(first_value(row, ["bb_type"])) == "ground_ball"), len(batted_ball_rows)),
        "batter_sprint_speed": _avg(rows, ["sprint_speed", "batter_sprint_speed"]),
        "source": str(source),
        "sourceUpdatedAt": _source_updated_at(source),
        "generatedAt": generated_at,
        "pregameSafe": True,
        "labelsExcluded": True,
        "warnings": "",
    }


def _normal_name(value: str) -> str:
    if "," in value:
        last, first = [part.strip() for part in value.split(",", 1)]
        return f"{first} {last}".strip()
    return value


def _plate_appearance_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if clean(first_value(row, ["events"]))]


def _event(row: dict[str, str]) -> str:
    return clean(first_value(row, ["events"])).lower()


def _rate(numerator: float, denominator: float) -> float | str:
    if denominator <= 0:
        return ""
    return round(numerator / denominator, 6)


def _avg(rows: list[dict[str, str]], aliases: list[str]) -> float | str:
    values = [to_float(first_value(row, aliases), 0.0) for row in rows if clean(first_value(row, aliases))]
    if not values:
        return ""
    return round(sum(values) / len(values), 6)


def _has_any_column(rows: list[dict[str, str]], aliases: list[str]) -> bool:
    return any(any(clean(row.get(alias)) for alias in aliases) for row in rows)


def _source_updated_at(path: Path) -> str:
    try:
        return date.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""
