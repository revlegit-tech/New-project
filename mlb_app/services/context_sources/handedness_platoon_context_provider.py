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
from mlb_app.services.player_prop_context_identity_service import normalize_opponent, normalize_player_name, normalize_team


HAND_PLATOON_FIELDS = [
    "date",
    "season",
    "player",
    "team",
    "opponent",
    "normalizedPlayer",
    "normalizedTeam",
    "normalizedOpponent",
    "subjectRole",
    "batter_hand",
    "pitcher_hand",
    "batter_avg_vs_hand",
    "batter_k_rate_vs_hand",
    "batter_recent_hits_vs_lhp",
    "batter_recent_hits_vs_rhp",
    "pitcher_avg_allowed_vs_hand",
    "source",
    "sourceUpdatedAt",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
]


class HandednessPlatoonContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "handedness_platoon", f"handedness_platoon_{date_label}.csv")
        batter_path = self._batter_log_path(season)
        pitcher_path = self._pitcher_log_path(season)
        warnings: list[str] = []
        if not batter_path.is_file():
            warnings.append("Local batter game log not found; handedness/platoon context unavailable.")
            write_csv_rows(output_path, [], HAND_PLATOON_FIELDS)
            return self._result("missing", date_label, season, 0, output_path, warnings)

        batter_rows = _pregame_rows(read_csv_rows(batter_path), date_label)
        pitcher_rows = _pregame_rows(read_csv_rows(pitcher_path), date_label) if pitcher_path.is_file() else []
        if not pitcher_path.is_file():
            warnings.append("Local pitcher game log not found; pitcher_hand and pitcher splits left null.")
        if batter_rows and not _has_any_column(batter_rows, ["bats", "stand", "batter_hand"]):
            warnings.append("Known batter handedness mappings unavailable; batter_hand left null.")
        if pitcher_rows and not _has_any_column(pitcher_rows, ["throws", "p_throws", "pitcher_hand"]):
            warnings.append("Known pitcher handedness mappings unavailable; pitcher_hand left null.")

        pitcher_hand_by_team = _latest_pitcher_hand_by_team(pitcher_rows)
        pitcher_avg_allowed = _pitcher_avg_allowed_by_team(pitcher_rows)
        generated_at = datetime.now(timezone.utc).isoformat()
        output = [
            _platoon_summary(date_label, season, player_rows, pitcher_hand_by_team, pitcher_avg_allowed, batter_path, generated_at)
            for player_rows in _group_player_rows(batter_rows)
        ]
        if not output:
            warnings.append("No prior batter rows available before target date.")
        for row in output:
            row_warnings = []
            if not row.get("batter_hand"):
                row_warnings.append("batter_hand unknown")
            if not row.get("pitcher_hand"):
                row_warnings.append("pitcher_hand unknown")
            row["warnings"] = "; ".join(row_warnings)
        write_csv_rows(output_path, output, HAND_PLATOON_FIELDS)
        return self._result(status_for_rows(len(output), warnings), date_label, season, len(output), output_path, warnings)

    def _batter_log_path(self, season: int) -> Path:
        cloud = self.settings.data_dir / "cloud" / "season_logs" / f"batter_game_logs_{season}.csv"
        warehouse = self.settings.data_dir / "warehouse" / "season_logs" / f"batter_game_logs_{season}.csv"
        return warehouse if warehouse.is_file() else cloud

    def _pitcher_log_path(self, season: int) -> Path:
        cloud = self.settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        warehouse = self.settings.data_dir / "warehouse" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        return warehouse if warehouse.is_file() else cloud

    def _result(self, status: str, date_label: str, season: int, rows: int, path: Path, warnings: list[str]) -> ContextProviderResult:
        return ContextProviderResult(
            status=status,
            date=date_label,
            season=season,
            source="handedness_platoon",
            rows=rows,
            path=str(path),
            warnings=warnings,
        )


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


def _group_player_rows(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        player = clean(first_value(row, ["player", "playerName", "name"]))
        if player:
            grouped[(key(player), clean(first_value(row, ["team", "teamAbbr"])))].append(row)
    return [sorted(value, key=lambda row: clean(first_value(row, ["date", "game_date", "gameDate"]))) for value in grouped.values()]


def _platoon_summary(
    date_label: str,
    season: int,
    rows: list[dict[str, str]],
    pitcher_hand_by_team: dict[str, str],
    pitcher_avg_allowed: dict[tuple[str, str], float | str],
    source: Path,
    generated_at: str,
) -> dict[str, Any]:
    latest = rows[-1]
    player = clean(first_value(latest, ["player", "playerName", "name"]))
    team = clean(first_value(latest, ["team", "teamAbbr"]))
    opponent = clean(first_value(latest, ["opponent", "opponentAbbr"]))
    pitcher_hand = pitcher_hand_by_team.get(key(opponent), "")
    split_rows = [row for row in rows if _normalized_hand(first_value(row, ["pitcher_hand", "p_throws", "throws"])) == pitcher_hand]
    lhp_rows = [row for row in rows[-10:] if _normalized_hand(first_value(row, ["pitcher_hand", "p_throws", "throws"])) == "L"]
    rhp_rows = [row for row in rows[-10:] if _normalized_hand(first_value(row, ["pitcher_hand", "p_throws", "throws"])) == "R"]
    return {
        "date": date_label,
        "season": season,
        "player": player,
        "team": team,
        "opponent": opponent,
        "normalizedPlayer": normalize_player_name(player),
        "normalizedTeam": normalize_team(team),
        "normalizedOpponent": normalize_opponent(opponent),
        "subjectRole": "batter",
        "batter_hand": _normalized_hand(first_value(latest, ["bats", "stand", "batter_hand"])),
        "pitcher_hand": pitcher_hand,
        "batter_avg_vs_hand": _avg(split_rows),
        "batter_k_rate_vs_hand": _k_rate(split_rows),
        "batter_recent_hits_vs_lhp": sum(to_float(first_value(row, ["hits", "h"])) for row in lhp_rows) if lhp_rows else "",
        "batter_recent_hits_vs_rhp": sum(to_float(first_value(row, ["hits", "h"])) for row in rhp_rows) if rhp_rows else "",
        "pitcher_avg_allowed_vs_hand": pitcher_avg_allowed.get((key(opponent), _normalized_hand(first_value(latest, ["bats", "stand", "batter_hand"]))), ""),
        "source": str(source),
        "sourceUpdatedAt": _source_updated_at(source),
        "generatedAt": generated_at,
        "pregameSafe": True,
        "labelsExcluded": True,
        "warnings": "",
    }


def _latest_pitcher_hand_by_team(rows: list[dict[str, str]]) -> dict[str, str]:
    hands: dict[str, str] = {}
    for row in rows:
        team = key(first_value(row, ["team", "teamAbbr"]))
        hand = _normalized_hand(first_value(row, ["throws", "p_throws", "pitcher_hand"]))
        if team and hand:
            hands[team] = hand
    return hands


def _pitcher_avg_allowed_by_team(rows: list[dict[str, str]]) -> dict[tuple[str, str], float | str]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        team = key(first_value(row, ["team", "teamAbbr"]))
        hand = _normalized_hand(first_value(row, ["batter_hand", "stand"]))
        if team and hand:
            grouped[(team, hand)].append(row)
    return {group_key: _avg(group_rows) for group_key, group_rows in grouped.items()}


def _avg(rows: list[dict[str, str]]) -> float | str:
    at_bats = sum(to_float(first_value(row, ["atBats", "at_bats", "battersFaced", "bf"])) for row in rows)
    hits = sum(to_float(first_value(row, ["hits", "h"])) for row in rows)
    if at_bats <= 0:
        return ""
    return round(hits / at_bats, 6)


def _k_rate(rows: list[dict[str, str]]) -> float | str:
    pa = sum(to_float(first_value(row, ["plateAppearances", "pa", "battersFaced", "bf"])) for row in rows)
    strikeouts = sum(to_float(first_value(row, ["strikeOuts", "strikeouts", "k"])) for row in rows)
    if pa <= 0:
        return ""
    return round(strikeouts / pa, 6)


def _normalized_hand(value: Any) -> str:
    text = clean(value).upper()
    if text in {"L", "LEFT", "LHP"}:
        return "L"
    if text in {"R", "RIGHT", "RHP"}:
        return "R"
    if text in {"S", "B", "SWITCH"}:
        return "S"
    return ""


def _has_any_column(rows: list[dict[str, str]], aliases: list[str]) -> bool:
    return any(any(clean(row.get(alias)) for alias in aliases) for row in rows)


def _source_updated_at(path: Path) -> str:
    try:
        return date.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""
