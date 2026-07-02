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
from mlb_app.services.player_prop_context_identity_service import align_board_context_identity, normalize_player_name, normalize_team


STATCAST_FIELDS = [
    "date",
    "season",
    "player",
    "player_mlbam_id",
    "pitcher",
    "pitcher_mlbam_id",
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
        diagnostics: dict[str, Any] = {
            "filesInspected": [],
            "rowsLoaded": 0,
            "pregameRows": 0,
            "rowsRejectedMissingPlayerIdentity": 0,
            "rowsRejectedMissingTeam": 0,
            "rowsRejectedAmbiguousIdentity": 0,
            "rowsMatchedToPlayerboardSubjects": 0,
            "sampleRejectedRows": [],
            "sampleMatchedRows": [],
        }
        board_index = _playerboard_subject_index(self.settings, date_label)
        for source_path in self._candidate_paths(date_label, season):
            rows = read_csv_rows(source_path)
            if not rows:
                continue
            diagnostics["filesInspected"].append({"path": str(source_path), "rowsLoaded": len(rows)})
            diagnostics["rowsLoaded"] += len(rows)
            pregame_rows = _pregame_rows(rows, date_label)
            if not pregame_rows:
                continue
            diagnostics["pregameRows"] += len(pregame_rows)
            generated_at = datetime.now(timezone.utc).isoformat()
            safe_rows = _safe_batter_rows(pregame_rows, board_index, diagnostics)
            output = [
                _statcast_summary(date_label, season, player_rows, source_path, generated_at)
                for player_rows in _group_batter_rows(safe_rows)
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
                diagnostics=diagnostics,
            )
        if diagnostics["rowsLoaded"]:
            warnings.append("No local Statcast artifact produced safely matched batter context rows; external Savant calls skipped.")
        else:
            warnings.append("No local Statcast artifact found; external Savant calls skipped.")
        write_csv_rows(output_path, [], STATCAST_FIELDS)
        return ContextProviderResult(status="missing", date=date_label, season=season, source="statcast", rows=0, path=str(output_path), warnings=warnings, diagnostics=diagnostics)

    def _candidate_paths(self, date_label: str, season: int) -> list[Path]:
        return [
            self.settings.data_dir / "features" / f"statcast_context_{date_label}.csv",
            self.settings.data_dir / "warehouse" / "statcast" / f"statcast_{season}.csv",
            self.settings.data_dir / "cache" / "statcast" / f"statcast_{season}.csv",
            *sorted((self.settings.data_dir / "cache" / "savant").glob(f"statcast_{season}_*.csv")),
            *sorted((self.settings.data_dir / "cache" / "savant" / "raw").glob(f"statcast_{season}_*.csv")),
            *sorted((self.settings.data_dir / "context" / "statcast").glob(f"*{season}*.csv")),
        ]


def _pregame_rows(rows: list[dict[str, str]], date_label: str) -> list[dict[str, str]]:
    try:
        target = date.fromisoformat(date_label)
    except ValueError:
        return []
    output: list[dict[str, str]] = []
    for row in rows:
        raw = clean(first_value(row, ["date", "game_date", "gameDate", "game_date_est"]))
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
        player = _batter_name(row)
        if not player:
            continue
        team = _batter_team(row)
        grouped[(key(player), team)].append(row)
    return list(grouped.values())


def _safe_batter_rows(
    rows: list[dict[str, str]],
    board_index: dict[str, Any],
    diagnostics: dict[str, Any],
) -> list[dict[str, str]]:
    safe: list[dict[str, str]] = []
    for row in rows:
        enriched = dict(row)
        player = _batter_name(enriched)
        team = _batter_team(enriched)
        player_id = clean(first_value(enriched, ["batter", "batter_id", "player_mlbam_id", "playerId"]))
        rejection = ""
        board_match: dict[str, str] | None = None
        if player and team:
            matches = (board_index.get("byNameTeam") or {}).get((normalize_player_name(player), normalize_team(team)), [])
            if len(matches) == 1:
                board_match = matches[0]
            elif len(matches) > 1:
                rejection = "ambiguous_identity"
        elif player_id:
            matches = (board_index.get("byPlayerId") or {}).get(player_id, [])
            if len(matches) == 1:
                board_match = matches[0]
                player = player or str(board_match.get("player") or "")
                team = team or str(board_match.get("team") or "")
            elif len(matches) > 1:
                rejection = "ambiguous_identity"

        if not player:
            rejection = rejection or "missing_player_identity"
        if not team:
            rejection = rejection or "missing_team"
        if rejection:
            _record_rejection(diagnostics, row, rejection)
            continue
        if board_index.get("hasBoard") and not board_match:
            _record_rejection(diagnostics, row, "ambiguous_identity")
            continue
        enriched["_safe_batter_name"] = player
        enriched["_safe_batter_team"] = team
        safe.append(enriched)
        if board_match:
            diagnostics["rowsMatchedToPlayerboardSubjects"] += 1
            _append_sample(diagnostics["sampleMatchedRows"], {"player": player, "team": team, "player_mlbam_id": player_id})
    return safe


def _record_rejection(diagnostics: dict[str, Any], row: dict[str, str], reason: str) -> None:
    if reason == "missing_player_identity":
        diagnostics["rowsRejectedMissingPlayerIdentity"] += 1
    elif reason == "missing_team":
        diagnostics["rowsRejectedMissingTeam"] += 1
    else:
        diagnostics["rowsRejectedAmbiguousIdentity"] += 1
    _append_sample(
        diagnostics["sampleRejectedRows"],
        {
            "reason": reason,
            "game_date": clean(first_value(row, ["date", "game_date", "gameDate"])),
            "player": _batter_name(row),
            "player_name": clean(row.get("player_name")),
            "batter": clean(first_value(row, ["batter", "batter_id"])),
            "team": _batter_team(row),
        },
    )


def _append_sample(samples: list[dict[str, Any]], row: dict[str, Any], limit: int = 5) -> None:
    if len(samples) < limit:
        samples.append(row)


def _statcast_summary(date_label: str, season: int, rows: list[dict[str, str]], source: Path, generated_at: str) -> dict[str, Any]:
    latest = rows[-1]
    player = _batter_name(latest)
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
        "player_mlbam_id": clean(first_value(latest, ["batter", "batter_id", "player_mlbam_id"])),
        "pitcher": _normal_name(clean(first_value(latest, ["pitcher_name", "pitcherPlayerName"]))),
        "pitcher_mlbam_id": clean(first_value(latest, ["pitcher", "pitcher_id", "pitcher_mlbam_id"])),
        "team": _batter_team(latest),
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


def _batter_name(row: dict[str, str]) -> str:
    safe = clean(row.get("_safe_batter_name"))
    if safe:
        return safe
    explicit = _normal_name(clean(first_value(row, ["player", "batter_name", "batterName", "name"])))
    if explicit:
        return explicit
    player_name = _normal_name(clean(first_value(row, ["player_name"])))
    if not player_name:
        return ""
    raw_pitcher_id = clean(first_value(row, ["pitcher", "pitcher_id"]))
    pitcher_name = clean(first_value(row, ["pitcher_name", "pitcherPlayerName"]))
    if raw_pitcher_id and not pitcher_name:
        return ""
    return player_name


def _batter_team(row: dict[str, str]) -> str:
    safe = clean(row.get("_safe_batter_team"))
    if safe:
        return safe
    explicit = clean(first_value(row, ["team", "bat_team", "batTeam", "batting_team"]))
    if explicit:
        return explicit
    half = clean(first_value(row, ["inning_topbot"])).lower()
    if half.startswith("top"):
        return clean(first_value(row, ["away_team", "awayTeam"]))
    if half.startswith("bot"):
        return clean(first_value(row, ["home_team", "homeTeam"]))
    return clean(first_value(row, ["away_team", "home_team", "awayTeam", "homeTeam"]))


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


def _playerboard_subject_index(settings: Settings, date_label: str) -> dict[str, Any]:
    rows, source = _playerboard_rows(settings, date_label)
    by_name_team: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    by_player_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        status = clean(row.get("attributionStatus")).lower()
        if status in {"invalid_player_label", "ambiguous", "conflict"}:
            continue
        aligned = align_board_context_identity(row)
        if aligned.get("subjectRole") not in {"batter", "unknown"}:
            continue
        player = clean(aligned.get("subjectName") or row.get("player"))
        normalized_player = clean(aligned.get("normalizedSubjectName")) or normalize_player_name(player)
        team = clean(aligned.get("subjectTeam") or row.get("team"))
        normalized_team = normalize_team(team)
        if not player or not normalized_player or not normalized_team:
            continue
        entry = {
            "player": player,
            "normalizedPlayer": normalized_player,
            "team": normalized_team,
            "source": source,
            "attributionStatus": status,
        }
        by_name_team[(normalized_player, normalized_team)].append(entry)
        player_id = clean(first_value(row, ["player_mlbam_id", "playerId", "player_id", "subjectPlayerId"]))
        if player_id:
            by_player_id[player_id].append(entry)
    return {"hasBoard": bool(rows), "source": source, "byNameTeam": by_name_team, "byPlayerId": by_player_id}


def _playerboard_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, str]], str]:
    root = settings.data_dir / "playerboard"
    candidates = [root / f"playerboard_{settings.current_season}.csv"]
    candidates.extend(sorted(root.glob("playerboard_*.csv"), key=lambda item: item.stat().st_mtime, reverse=True))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        rows = [
            row
            for row in read_csv_rows(path)
            if not clean(first_value(row, ["date", "eventDateLocal", "game_date"])) or clean(first_value(row, ["date", "eventDateLocal", "game_date"]))[:10] == date_label
        ]
        if rows:
            return rows, str(path)
    return [], ""
