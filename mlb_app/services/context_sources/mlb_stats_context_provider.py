from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date
from datetime import datetime, timezone
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
from mlb_app.services.player_prop_context_identity_service import (
    align_board_context_identity,
    clean_subject_name,
    normalize_opponent,
    normalize_player_name,
    normalize_team,
)


PLAYER_RECENT_FORM_FIELDS = [
    "date",
    "season",
    "player",
    "team",
    "normalizedPlayer",
    "normalizedTeam",
    "opponent",
    "normalizedOpponent",
    "subjectRole",
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
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
    "seedSource",
    "seedRowCount",
    "historicalSource",
    "recentWindow",
]

PITCHER_CONTEXT_FIELDS = [
    "date",
    "season",
    "pitcher",
    "team",
    "normalizedPitcher",
    "normalizedTeam",
    "opponent",
    "normalizedOpponent",
    "subjectRole",
    "pitcher_recent_games",
    "pitcher_k_rate",
    "pitcher_walk_rate",
    "pitcher_hr_rate",
    "pitcher_babip",
    "pitcher_days_rest",
    "pitcher_velo_delta",
    "source",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
    "seedSource",
    "seedRowCount",
    "historicalSource",
    "recentWindow",
]


class MLBStatsContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def player_recent_form(self, *, date_label: str, season: int) -> ContextProviderResult:
        path = context_path(self.settings, "player_recent_form", f"player_recent_form_{date_label}.csv")
        warnings: list[str] = []
        seed_rows, seed_diagnostics = self._seed_rows(date_label=date_label, season=season, wanted_role="batter")
        historical = self._historical_rows(self._batter_log_paths(season), date_label=date_label)
        rows = historical["before"]
        source = Path(historical["source"] or "")
        if not historical["pathsChecked"]:
            warnings.append("Local batter game log not found.")
        if rows and (
            not _has_any_column(rows, ["strikeOuts", "strikeouts", "k"])
            or not _has_any_column(rows, ["plateAppearances", "pa"])
        ):
            warnings.append("rolling_k_rate_10 unavailable from local batter logs; field left null where unsafe.")
        grouped = _group_player_rows(rows)
        if not seed_rows:
            seed_rows = [_seed_from_history(player_rows, "batter") for player_rows in grouped.values()]
        generated_at = datetime.now(timezone.utc).isoformat()
        output = [
            _batter_summary(
                date_label,
                season,
                seed,
                grouped.get((seed["normalizedPlayer"], seed["normalizedTeam"])) or [],
                source,
                generated_at,
            )
            for seed in seed_rows
        ]
        if not rows:
            warnings.append("No prior batter game logs available before target date.")
        if not seed_rows:
            warnings.append("No current board batter subjects available for player_recent_form.")
        write_csv_rows(path, output, PLAYER_RECENT_FORM_FIELDS)
        diagnostics = _player_diagnostics(date_label, season, seed_diagnostics, historical, output, seed_rows, warnings)
        return self._result(
            status_for_rows(len(output), warnings),
            date_label,
            season,
            "player_recent_form",
            len(output),
            path,
            warnings,
            diagnostics,
        )

    def pitcher_context(self, *, date_label: str, season: int) -> ContextProviderResult:
        path = context_path(self.settings, "pitcher_context", f"pitcher_context_{date_label}.csv")
        warnings: list[str] = []
        seed_rows, seed_diagnostics = self._seed_rows(date_label=date_label, season=season, wanted_role="pitcher")
        historical = self._historical_rows(self._pitcher_log_paths(season), date_label=date_label)
        rows = historical["before"]
        source = Path(historical["source"] or "")
        if not historical["pathsChecked"]:
            warnings.append("Local pitcher game log not found.")
        if rows and not _has_any_column(rows, ["battersFaced", "batters_faced", "bf"]):
            warnings.append("Pitcher rate denominators unavailable from local pitcher logs; rate fields left null where unsafe.")
        if rows and not _has_any_column(rows, ["releaseSpeed", "release_speed", "avgFastballVelo", "fastballVelo"]):
            warnings.append("pitcher_velo_delta unavailable from local pitcher logs; field left null.")
        grouped = _group_pitcher_rows(rows)
        if not seed_rows:
            seed_rows = [_seed_from_history(pitcher_rows, "pitcher") for pitcher_rows in grouped.values()]
        generated_at = datetime.now(timezone.utc).isoformat()
        output = [
            _pitcher_summary(
                date_label,
                season,
                seed,
                grouped.get((seed["normalizedPlayer"], seed["normalizedTeam"])) or [],
                source,
                generated_at,
            )
            for seed in seed_rows
        ]
        if not rows:
            warnings.append("No prior pitcher game logs available before target date.")
        if not seed_rows:
            warnings.append("No current board pitcher subjects available for pitcher_context.")
        write_csv_rows(path, output, PITCHER_CONTEXT_FIELDS)
        diagnostics = _pitcher_diagnostics(date_label, season, seed_diagnostics, historical, output, seed_rows, warnings)
        return self._result(
            _pitcher_status(len(output), warnings),
            date_label,
            season,
            "pitcher_context",
            len(output),
            path,
            warnings,
            diagnostics,
        )

    def _batter_log_paths(self, season: int) -> list[Path]:
        return [
            self.settings.data_dir / "cache" / "incremental_stats" / f"batter_game_logs_{season}.csv",
            self.settings.data_dir / "warehouse" / "season_logs" / f"batter_game_logs_{season}.csv",
            self.settings.data_dir / "cloud" / "season_logs" / f"batter_game_logs_{season}.csv",
        ]

    def _pitcher_log_paths(self, season: int) -> list[Path]:
        return [
            self.settings.data_dir / "cache" / "incremental_stats" / f"pitcher_game_logs_{season}.csv",
            self.settings.data_dir / "warehouse" / "season_logs" / f"pitcher_game_logs_{season}.csv",
            self.settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv",
        ]

    def _historical_rows(self, paths: list[Path], *, date_label: str) -> dict[str, Any]:
        checked = [str(path) for path in paths if path.is_file()]
        for path in paths:
            if not path.is_file():
                continue
            rows = read_csv_rows(path)
            dated = _split_rows_by_date(rows, date_label)
            if rows:
                return {
                    "source": str(path),
                    "pathsChecked": checked,
                    "rowsLoaded": len(rows),
                    **dated,
                }
        return {
            "source": "",
            "pathsChecked": checked,
            "rowsLoaded": 0,
            "before": [],
            "beforeCount": 0,
            "sameDayRejected": 0,
            "futureRejected": 0,
            "invalidDateRejected": 0,
        }

    def _seed_rows(self, *, date_label: str, season: int, wanted_role: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        sources = [
            (self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv", "playerboard", ("date", "game_date", "gameDate", "event_date")),
            (self.settings.data_dir / "odds" / f"propline_props_{date_label}.csv", "propline_props", ("eventDateLocal", "date")),
        ]
        raw_rows: list[dict[str, str]] = []
        seed_path = sources[0][0]
        source_mode = "none"
        for candidate_path, candidate_mode, date_aliases in sources:
            candidate_rows = _read_date_rows(candidate_path, date_label, date_aliases=date_aliases)
            if candidate_rows:
                raw_rows = candidate_rows
                seed_path = candidate_path
                source_mode = candidate_mode
                break
        diagnostics: dict[str, Any] = {
            "providerSourceMode": source_mode,
            "providerSeedPath": str(seed_path),
            "providerSeedRows": len(raw_rows),
            "providerSeedDate": date_label,
            "providerSeedSlateMatchesTargetDate": bool(raw_rows),
            "providerSeedBatterRows": 0,
            "providerSeedPitcherRows": 0,
            "boardSeedSkippedRows": 0,
            "boardSeedSkipReasons": {},
        }
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        skip_reasons: Counter[str] = Counter()
        for raw in raw_rows:
            aligned = align_board_context_identity(raw)
            role = clean(aligned.get("subjectRole")).lower() or "unknown"
            if role == "batter":
                diagnostics["providerSeedBatterRows"] += 1
            elif role == "pitcher":
                diagnostics["providerSeedPitcherRows"] += 1
            if role != wanted_role:
                skip_reasons["role_not_applicable"] += 1
                continue
            player = clean(aligned.get("subjectName"))
            player, _ = clean_subject_name(player, first_value(aligned, ["baseMarket", "originalMarket", "market"]))
            normalized_player = clean(aligned.get("normalizedSubjectName")) or normalize_player_name(player)
            team = clean(aligned.get("subjectTeam"))
            normalized_team = clean(aligned.get("normalizedSubjectTeam")) or normalize_team(team)
            opponent = clean(aligned.get("subjectOpponent"))
            normalized_opponent = clean(aligned.get("normalizedSubjectOpponent")) or normalize_opponent(opponent)
            if not normalized_player:
                skip_reasons["missing_subject_identity"] += 1
                continue
            if not normalized_team:
                skip_reasons["missing_subject_team"] += 1
                continue
            seed = deduped.setdefault(
                (normalized_player, normalized_team),
                {
                    "player": player,
                    "team": team or normalized_team,
                    "normalizedPlayer": normalized_player,
                    "normalizedTeam": normalized_team,
                    "opponent": opponent,
                    "normalizedOpponent": normalized_opponent,
                    "subjectRole": wanted_role,
                    "seedSource": source_mode,
                    "seedRowCount": 0,
                },
            )
            seed["seedRowCount"] = int(seed.get("seedRowCount") or 0) + 1
        diagnostics["boardSeedSkippedRows"] = sum(skip_reasons.values())
        diagnostics["boardSeedSkipReasons"] = dict(sorted(skip_reasons.items()))
        diagnostics["contextRowsDeduped"] = max(
            (diagnostics["providerSeedBatterRows"] if wanted_role == "batter" else diagnostics["providerSeedPitcherRows"]) - len(deduped),
            0,
        )
        return list(deduped.values()), diagnostics

    def _result(
        self,
        status: str,
        date_label: str,
        season: int,
        source: str,
        rows: int,
        path: Path,
        warnings: list[str],
        diagnostics: dict[str, Any] | None = None,
    ) -> ContextProviderResult:
        return ContextProviderResult(
            status=status,
            date=date_label,
            season=season,
            source=source,
            rows=rows,
            path=str(path),
            warnings=warnings,
            diagnostics=diagnostics or {},
        )


def _parse_row_date(row: dict[str, Any]) -> date | None:
    raw = clean(first_value(row, ["date", "game_date", "gameDate", "eventDateLocal", "event_date"]))
    if not raw:
        return None
    text = raw[:10].replace("/", "-")
    for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            if fmt == "%Y-%m-%d":
                return date.fromisoformat(text)
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return None


def _split_rows_by_date(rows: list[dict[str, str]], date_label: str) -> dict[str, Any]:
    try:
        target = date.fromisoformat(date_label)
    except ValueError:
        return {"before": [], "beforeCount": 0, "sameDayRejected": 0, "futureRejected": 0, "invalidDateRejected": len(rows)}
    prior: list[dict[str, str]] = []
    same_day = 0
    future = 0
    invalid = 0
    for row in rows:
        row_date = _parse_row_date(row)
        if row_date is None:
            invalid += 1
            continue
        if row_date < target:
            prior.append(row)
        elif row_date == target:
            same_day += 1
        else:
            future += 1
    return {
        "before": prior,
        "beforeCount": len(prior),
        "sameDayRejected": same_day,
        "futureRejected": future,
        "invalidDateRejected": invalid,
    }


def _group_player_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        player = clean(first_value(row, ["player", "playerName", "name"]))
        normalized_player = normalize_player_name(player)
        normalized_team = normalize_team(first_value(row, ["team", "teamAbbr"]))
        if not player:
            continue
        grouped[(normalized_player, normalized_team)].append(row)
    return {group_key: _sort_rows(value) for group_key, value in grouped.items()}


def _group_pitcher_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    return _group_player_rows(rows)


def _sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: clean(first_value(row, ["date", "game_date", "gameDate"])))


def _batter_summary(
    date_label: str,
    season: int,
    seed: dict[str, Any],
    rows: list[dict[str, str]],
    source: Path,
    generated_at: str,
) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    player = clean(seed.get("player")) or clean(first_value(latest, ["player", "playerName", "name"]))
    team = clean(seed.get("team")) or clean(first_value(latest, ["team", "teamAbbr"]))
    at_bats = sum(to_float(first_value(row, ["atBats", "at_bats", "ab"])) for row in rows)
    hits = sum(to_float(first_value(row, ["hits", "h"])) for row in rows)
    strikeouts_10 = sum(to_float(first_value(row, ["strikeOuts", "strikeouts", "k"])) for row in rows[-10:])
    pa_10 = sum(to_float(first_value(row, ["plateAppearances", "pa"])) for row in rows[-10:])
    row_warnings = [] if rows else ["missing_historical_data"]
    return {
        "date": date_label,
        "season": season,
        "player": player,
        "team": team,
        "normalizedPlayer": clean(seed.get("normalizedPlayer")) or normalize_player_name(player),
        "normalizedTeam": clean(seed.get("normalizedTeam")) or normalize_team(team),
        "opponent": clean(seed.get("opponent")),
        "normalizedOpponent": clean(seed.get("normalizedOpponent")) or normalize_opponent(seed.get("opponent")),
        "subjectRole": "batter",
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
        "generatedAt": generated_at,
        "pregameSafe": True,
        "labelsExcluded": True,
        "warnings": "; ".join(row_warnings),
        "seedSource": clean(seed.get("seedSource")),
        "seedRowCount": seed.get("seedRowCount", ""),
        "historicalSource": str(source),
        "recentWindow": "strictly before target date; last 5/10/15 player games",
    }


def _pitcher_summary(
    date_label: str,
    season: int,
    seed: dict[str, Any],
    rows: list[dict[str, str]],
    source: Path,
    generated_at: str,
) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    pitcher = clean(seed.get("player")) or clean(first_value(latest, ["player", "pitcher", "playerName", "name"]))
    team = clean(seed.get("team")) or clean(first_value(latest, ["team", "teamAbbr"]))
    batters = sum(to_float(first_value(row, ["battersFaced", "batters_faced", "bf"])) for row in rows)
    strikeouts = sum(to_float(first_value(row, ["strikeOuts", "strikeouts", "k"])) for row in rows)
    walks = sum(to_float(first_value(row, ["baseOnBalls", "walks", "bb"])) for row in rows)
    homers = sum(to_float(first_value(row, ["homeRuns", "home_runs", "hr"])) for row in rows)
    hits = sum(to_float(first_value(row, ["hits", "h"])) for row in rows)
    balls_in_play = batters - strikeouts - walks - homers
    days_rest = ""
    if rows:
        row_date = _parse_row_date(rows[-1])
        if row_date is not None:
            days_rest = (date.fromisoformat(date_label) - row_date).days
    row_warnings = ["pitcher_velo_delta unavailable"] if rows else ["missing_historical_data", "pitcher_velo_delta unavailable"]
    return {
        "date": date_label,
        "season": season,
        "pitcher": pitcher,
        "team": team,
        "normalizedPitcher": clean(seed.get("normalizedPlayer")) or normalize_player_name(pitcher),
        "normalizedTeam": clean(seed.get("normalizedTeam")) or normalize_team(team),
        "opponent": clean(seed.get("opponent")),
        "normalizedOpponent": clean(seed.get("normalizedOpponent")) or normalize_opponent(seed.get("opponent")),
        "subjectRole": "pitcher",
        "pitcher_recent_games": len(rows),
        "pitcher_k_rate": _rate(strikeouts, batters),
        "pitcher_walk_rate": _rate(walks, batters),
        "pitcher_hr_rate": _rate(homers, batters),
        "pitcher_babip": _rate(hits - homers, balls_in_play),
        "pitcher_days_rest": days_rest,
        "pitcher_velo_delta": "",
        "source": str(source),
        "generatedAt": generated_at,
        "pregameSafe": True,
        "labelsExcluded": True,
        "warnings": "; ".join(row_warnings),
        "seedSource": clean(seed.get("seedSource")),
        "seedRowCount": seed.get("seedRowCount", ""),
        "historicalSource": str(source),
        "recentWindow": "strictly before target date; season-to-date prior pitcher games",
    }


def _rate(numerator: float, denominator: float) -> float | str:
    if denominator <= 0:
        return ""
    return round(numerator / denominator, 6)


def _has_any_column(rows: list[dict[str, str]], aliases: list[str]) -> bool:
    return any(any(clean(row.get(alias)) for alias in aliases) for row in rows)


def _pitcher_status(rows: int, warnings: list[str]) -> str:
    if rows <= 0:
        return "missing"
    material_warnings = [
        warning
        for warning in warnings
        if not warning.startswith("pitcher_velo_delta unavailable")
    ]
    return "partial" if material_warnings else "ok"


def _read_date_rows(path: Path, date_label: str, date_aliases: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_date = clean(first_value(row, list(date_aliases)))
            if raw_date[:10] == date_label:
                rows.append(dict(row))
    return rows


def _base_diagnostics(
    date_label: str,
    season: int,
    seed_diagnostics: dict[str, Any],
    historical: dict[str, Any],
    output: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    seed_keys = {_context_key(seed, date_label, season) for seed in seed_rows}
    output_keys = {_context_key(row, date_label, season) for row in output}
    return {
        **seed_diagnostics,
        "historicalSourcePathsChecked": historical.get("pathsChecked") or [],
        "historicalSourceRowsLoaded": historical.get("rowsLoaded", 0),
        "historicalRowsBeforeTargetDate": historical.get("beforeCount", 0),
        "historicalRowsRejectedSameDay": historical.get("sameDayRejected", 0),
        "historicalRowsRejectedFuture": historical.get("futureRejected", 0),
        "historicalRowsRejectedInvalidDate": historical.get("invalidDateRejected", 0),
        "rowsGenerated": len(output),
        "rowsGeneratedFromBoard": len(output) if seed_diagnostics.get("providerSourceMode") == "playerboard" else 0,
        "rowsMatchingBoardSubjects": len(output_keys.intersection(seed_keys)),
        "boardSubjectsWithoutContextRows": len(seed_keys - output_keys),
        "externalApiCallsMade": 0,
        "pregameSafe": True,
        "labelsExcluded": True,
        "warnings": sorted(set(warnings)),
    }


def _player_diagnostics(
    date_label: str,
    season: int,
    seed_diagnostics: dict[str, Any],
    historical: dict[str, Any],
    output: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    diagnostics = _base_diagnostics(date_label, season, seed_diagnostics, historical, output, seed_rows, warnings)
    diagnostics.update(
        {
            "playerRowsSeededFromBoard": len(seed_rows) if seed_diagnostics.get("providerSourceMode") == "playerboard" else 0,
            "playerRowsWithHistoricalData": sum(1 for row in output if to_float(row.get("recent_games")) > 0),
            "playerRowsMissingHistoricalData": sum(1 for row in output if to_float(row.get("recent_games")) <= 0),
            "playerRowsWithRollingAvg5": _populated_count(output, "rolling_avg_5"),
            "playerRowsWithRollingAvg10": _populated_count(output, "rolling_avg_10"),
            "playerRowsWithRollingAvg15": _populated_count(output, "rolling_avg_15"),
            "playerRowsWithRollingTb10": _populated_count(output, "rolling_total_bases_10"),
            "playerRowsWithRollingHrRate15": _populated_count(output, "rolling_hr_rate_15"),
            "playerRowsWithRollingKRate10": _populated_count(output, "rolling_k_rate_10"),
            "historicalRowsUsed": historical.get("beforeCount", 0),
            "sourceCounts": dict(Counter(clean(row.get("source")) for row in output if clean(row.get("source")))),
            "sampleRowsWithRecentForm": [_sample(row) for row in output if to_float(row.get("recent_games")) > 0][:10],
            "sampleRowsMissingRecentForm": [_sample(row) for row in output if to_float(row.get("recent_games")) <= 0][:10],
        }
    )
    return diagnostics


def _pitcher_diagnostics(
    date_label: str,
    season: int,
    seed_diagnostics: dict[str, Any],
    historical: dict[str, Any],
    output: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    diagnostics = _base_diagnostics(date_label, season, seed_diagnostics, historical, output, seed_rows, warnings)
    diagnostics.update(
        {
            "pitcherRowsSeededFromBoard": len(seed_rows) if seed_diagnostics.get("providerSourceMode") == "playerboard" else 0,
            "pitcherRowsWithHistoricalData": sum(1 for row in output if to_float(row.get("pitcher_recent_games")) > 0),
            "pitcherRowsMissingHistoricalData": sum(1 for row in output if to_float(row.get("pitcher_recent_games")) <= 0),
            "pitcherRowsWithRecentGames": _populated_count(output, "pitcher_recent_games"),
            "pitcherRowsWithKRate": _populated_count(output, "pitcher_k_rate"),
            "pitcherRowsWithWalkRate": _populated_count(output, "pitcher_walk_rate"),
            "pitcherRowsWithHrRate": _populated_count(output, "pitcher_hr_rate"),
            "pitcherRowsWithBabip": _populated_count(output, "pitcher_babip"),
            "pitcherRowsWithDaysRest": _populated_count(output, "pitcher_days_rest"),
            "pitcherRowsWithVeloDelta": _populated_count(output, "pitcher_velo_delta"),
            "historicalRowsUsed": historical.get("beforeCount", 0),
            "sourceCounts": dict(Counter(clean(row.get("source")) for row in output if clean(row.get("source")))),
            "sampleRowsWithPitcherContext": [_sample(row) for row in output if to_float(row.get("pitcher_recent_games")) > 0][:10],
            "sampleRowsMissingPitcherContext": [_sample(row) for row in output if to_float(row.get("pitcher_recent_games")) <= 0][:10],
        }
    )
    return diagnostics


def _populated_count(rows: list[dict[str, Any]], field: str) -> int:
    return sum(1 for row in rows if clean(row.get(field)))


def _context_key(row: dict[str, Any], date_label: str, season: int) -> str:
    return "|".join(
        [
            date_label,
            str(season),
            clean(row.get("normalizedPlayer")) or clean(row.get("normalizedPitcher")) or normalize_player_name(row.get("player") or row.get("pitcher")),
            clean(row.get("normalizedTeam")) or normalize_team(row.get("team")),
        ]
    )


def _sample(row: dict[str, Any]) -> dict[str, str]:
    return {
        "player": clean(row.get("player") or row.get("pitcher")),
        "team": clean(row.get("team")),
        "opponent": clean(row.get("opponent")),
        "normalizedPlayer": clean(row.get("normalizedPlayer") or row.get("normalizedPitcher")),
        "normalizedTeam": clean(row.get("normalizedTeam")),
        "normalizedOpponent": clean(row.get("normalizedOpponent")),
    }


def _seed_from_history(rows: list[dict[str, str]], role: str) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    player = clean(first_value(latest, ["player", "pitcher", "playerName", "name"]))
    team = clean(first_value(latest, ["team", "teamAbbr"]))
    opponent = clean(first_value(latest, ["opponent", "opponentAbbr"]))
    return {
        "player": player,
        "team": team,
        "normalizedPlayer": normalize_player_name(player),
        "normalizedTeam": normalize_team(team),
        "opponent": opponent,
        "normalizedOpponent": normalize_opponent(opponent),
        "subjectRole": role,
        "seedSource": "historical_fallback",
        "seedRowCount": len(rows),
    }
