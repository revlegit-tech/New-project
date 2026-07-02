from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings


CONTEXT_STATUSES = {"ok", "partial", "missing", "error", "neutral_fallback"}


@dataclass
class ContextProviderResult:
    status: str
    date: str
    season: int
    source: str
    rows: int
    path: str
    generatedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    externalApiCallsMade: int = 0
    pregameSafe: bool = True
    labelsExcluded: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    criticalForBoard: bool = True
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in CONTEXT_STATUSES:
            raise ValueError(f"Unsupported context provider status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "date": self.date,
            "season": int(self.season),
            "source": self.source,
            "rows": int(self.rows),
            "path": self.path,
            "generatedAt": self.generatedAt,
            "externalApiCallsMade": int(self.externalApiCallsMade),
            "pregameSafe": bool(self.pregameSafe),
            "labelsExcluded": bool(self.labelsExcluded),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "criticalForBoard": bool(self.criticalForBoard),
            "diagnostics": dict(self.diagnostics),
        }


def context_path(settings: Settings, group: str, filename: str) -> Path:
    return settings.data_dir / "context" / group / filename


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        text = str(value).replace("+", "").strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def first_value(row: dict[str, Any], aliases: list[str], default: Any = "") -> Any:
    for alias in aliases:
        value = row.get(alias)
        if clean(value):
            return value
    return default


def key(value: Any) -> str:
    return " ".join(clean(value).lower().split())


def team_key(value: Any) -> str:
    return "".join(ch for ch in clean(value).lower() if ch.isalnum())


def status_for_rows(rows: int, warnings: list[str]) -> str:
    if rows <= 0:
        return "missing"
    return "partial" if warnings else "ok"


def cached_schedule_games(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], str]:
    for path in (
        settings.data_dir / "cache" / "incremental_stats" / "raw" / "schedules" / f"schedule_{date_label}.json",
        settings.data_dir / "cache" / "season_stats" / "raw" / f"schedule_{date_label}.json",
        settings.data_dir / "warehouse" / "raw" / f"schedule_{date_label}.json",
    ):
        games = _read_schedule_path(path, date_label)
        if games:
            return games, str(path)
    return [], ""


def schedule_side_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], str]:
    games, source = cached_schedule_games(settings, date_label)
    rows: list[dict[str, Any]] = []
    for game in games:
        game_pk = clean(game.get("game_pk") or game.get("gamePk"))
        home = clean(game.get("home_team") or game.get("homeTeam"))
        away = clean(game.get("away_team") or game.get("awayTeam"))
        venue = clean(game.get("venue"))
        if not home or not away:
            continue
        rows.append({"game_pk": game_pk, "team": away, "opponent": home, "home_team": home, "away_team": away, "venue": venue})
        rows.append({"game_pk": game_pk, "team": home, "opponent": away, "home_team": home, "away_team": away, "venue": venue})
    if rows:
        return _dedupe_side_rows(rows), source

    rows, source = _context_game_side_rows(settings, date_label)
    if rows:
        return _dedupe_side_rows(rows), source

    rows, source = _propline_side_rows(settings, date_label)
    if rows:
        return _dedupe_side_rows(rows), source

    rows, source = _playerboard_side_rows(settings, date_label)
    if rows:
        return _dedupe_side_rows(rows), source

    return [], ""


def _read_schedule_path(path: Path, date_label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_games: list[Any] = []
    if isinstance(payload, dict):
        for day in payload.get("dates") or []:
            if not isinstance(day, dict):
                continue
            if clean(day.get("date")) and clean(day.get("date")) != date_label:
                continue
            raw_games.extend(day.get("games") or [])
        if not raw_games:
            raw_games = payload.get("games") or payload.get("items") or []
    elif isinstance(payload, list):
        raw_games = payload
    games: list[dict[str, Any]] = []
    for game in raw_games:
        if isinstance(game, dict):
            normalized = _normalize_schedule_game(game)
            if normalized:
                games.append(normalized)
    return games


def _context_game_side_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], str]:
    paths = [
        settings.data_dir / "warehouse" / "game_context" / f"game_context_{date_label}.csv",
        settings.data_dir / "warehouse" / "game_context" / f"game_context_markets_{date_label}.csv",
        settings.data_dir / "warehouse" / "summaries" / f"games_{date_label}.json",
        settings.data_dir / "warehouse" / "game_context" / f"mlb_schedule_{date_label}.json",
    ]
    for path in paths:
        if path.suffix.lower() == ".json":
            games = _read_schedule_path(path, date_label)
            rows = _side_rows_from_games(games)
        else:
            rows = _csv_side_rows(path, date_label=date_label, require_date=True, skip_invalid_player_labels=False)
        if rows:
            return rows, str(path)
    return [], ""


def _propline_side_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], str]:
    path = settings.data_dir / "odds" / f"propline_props_{date_label}.csv"
    return _csv_side_rows(path, date_label=date_label, require_date=False, skip_invalid_player_labels=False), str(path) if path.is_file() else ""


def _playerboard_side_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], str]:
    path = settings.data_dir / "playerboard" / f"playerboard_{settings.current_season}.csv"
    if not path.is_file():
        candidates = sorted((settings.data_dir / "playerboard").glob("playerboard_*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
        path = candidates[0] if candidates else path
    return _csv_side_rows(path, date_label=date_label, require_date=True, skip_invalid_player_labels=True), str(path) if path.is_file() else ""


def _side_rows_from_games(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for game in games:
        game_pk = clean(game.get("game_pk") or game.get("gamePk"))
        home = clean(game.get("home_team") or game.get("homeTeam") or game.get("home"))
        away = clean(game.get("away_team") or game.get("awayTeam") or game.get("away"))
        venue = clean(game.get("venue"))
        if not home or not away:
            continue
        rows.append({"game_pk": game_pk, "team": away, "opponent": home, "home_team": home, "away_team": away, "venue": venue})
        rows.append({"game_pk": game_pk, "team": home, "opponent": away, "home_team": home, "away_team": away, "venue": venue})
    return rows


def _csv_side_rows(path: Path, *, date_label: str, require_date: bool, skip_invalid_player_labels: bool) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for row in read_csv_rows(path):
        row_date = clean(first_value(row, ["eventDateLocal", "date", "game_date", "gameDate"]))[:10]
        if require_date and row_date != date_label:
            continue
        if row_date and row_date != date_label:
            continue
        if skip_invalid_player_labels and clean(row.get("attributionStatus")).lower() == "invalid_player_label":
            continue
        home = clean(first_value(row, ["home_team", "homeTeam", "home"]))
        away = clean(first_value(row, ["away_team", "awayTeam", "away"]))
        team = clean(first_value(row, ["team", "resolvedTeam", "resolvedTeamAbbr", "sourceTeam"]))
        opponent = clean(first_value(row, ["opponent", "resolvedOpponent", "resolvedOpponentAbbr", "sourceOpponent"]))
        if home and away:
            game_pk = clean(first_value(row, ["game_pk", "gamePk", "game_id", "gameId", "event_id", "eventId", "resolvedGameId"]))
            venue = clean(row.get("venue"))
            rows.append({"game_pk": game_pk, "team": away, "opponent": home, "home_team": home, "away_team": away, "venue": venue})
            rows.append({"game_pk": game_pk, "team": home, "opponent": away, "home_team": home, "away_team": away, "venue": venue})
            continue
        if team and opponent:
            game_pk = clean(first_value(row, ["game_pk", "gamePk", "game_id", "gameId", "event_id", "eventId", "resolvedGameId"]))
            venue = clean(row.get("venue"))
            rows.append({"game_pk": game_pk, "team": team, "opponent": opponent, "home_team": home, "away_team": away, "venue": venue})
    return rows


def _dedupe_side_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        team = clean(row.get("team"))
        opponent = clean(row.get("opponent"))
        if not team or not opponent:
            continue
        game_pk = clean(row.get("game_pk"))
        deduped.setdefault((game_pk, team_key(team), team_key(opponent)), row)
    return list(deduped.values())


def _normalize_schedule_game(game: dict[str, Any]) -> dict[str, Any]:
    teams = game.get("teams") if isinstance(game.get("teams"), dict) else {}
    home_team = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away_team = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    home_info = home_team.get("team") if isinstance(home_team.get("team"), dict) else {}
    away_info = away_team.get("team") if isinstance(away_team.get("team"), dict) else {}
    venue = game.get("venue") if isinstance(game.get("venue"), dict) else {}
    home = first_value(game, ["home_team", "homeTeam", "home"]) or first_value(home_info, ["abbreviation", "fileCode", "teamCode"])
    away = first_value(game, ["away_team", "awayTeam", "away"]) or first_value(away_info, ["abbreviation", "fileCode", "teamCode"])
    if not clean(home) or not clean(away):
        return {}
    return {
        "game_pk": first_value(game, ["game_pk", "gamePk", "game_id", "gameId", "event_id"]),
        "home_team": clean(home).upper(),
        "away_team": clean(away).upper(),
        "venue": first_value(game, ["venue"]) if not isinstance(game.get("venue"), dict) else clean(venue.get("name")),
    }
