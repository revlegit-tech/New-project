from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import (
    ContextProviderResult,
    clean,
    context_path,
    first_value,
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
from mlb_app.services.player_attribution import apply_attribution
from mlb_app.services.player_handedness_lookup_service import PlayerHandednessLookupService


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
    "opposingPitcher",
    "normalizedOpposingPitcher",
    "opposingPitcherTeam",
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
    "seedSource",
    "seedMarketCount",
    "seedRowCount",
    "seedSubjectNameSource",
    "enrichmentStatus",
]


class HandednessPlatoonContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "handedness_platoon", f"handedness_platoon_{date_label}.csv")
        batter_path = self._batter_log_path(season)
        pitcher_path = self._pitcher_log_path(season)
        warnings: list[str] = []
        seed_rows, seed_diagnostics = self._seed_rows(date_label=date_label, season=season)
        if not seed_rows:
            warnings.append("No current board batter subjects available; handedness/platoon context unavailable.")
            write_csv_rows(output_path, [], HAND_PLATOON_FIELDS)
            diagnostics = self._diagnostics(date_label, season, seed_diagnostics, [], [])
            return self._result("missing", date_label, season, 0, output_path, warnings, diagnostics)

        batter_rows = _pregame_rows(read_csv_rows(batter_path), date_label) if batter_path.is_file() else []
        pitcher_rows = _pregame_rows(read_csv_rows(pitcher_path), date_label) if pitcher_path.is_file() else []
        cache_batter_path = self.settings.data_dir / "cache" / "incremental_stats" / f"batter_game_logs_{season}.csv"
        cache_pitcher_path = self.settings.data_dir / "cache" / "incremental_stats" / f"pitcher_game_logs_{season}.csv"
        cache_batter_rows = _pregame_rows(read_csv_rows(cache_batter_path), date_label) if cache_batter_path.is_file() else []
        cache_pitcher_rows = _pregame_rows(read_csv_rows(cache_pitcher_path), date_label) if cache_pitcher_path.is_file() else []
        if not batter_path.is_file():
            warnings.append("Local batter game log not found; handedness and split fields left null.")
        if not pitcher_path.is_file():
            warnings.append("Local pitcher game log not found; pitcher_hand and pitcher splits left null.")
        all_batter_rows = batter_rows + cache_batter_rows
        all_pitcher_rows = pitcher_rows + cache_pitcher_rows
        if all_batter_rows and not _has_any_column(all_batter_rows, ["bats", "stand", "batter_hand"]):
            warnings.append("Known batter handedness mappings unavailable in game-log CSVs; checking local Statcast cache.")
        if all_pitcher_rows and not _has_any_column(all_pitcher_rows, ["throws", "p_throws", "pitcher_hand"]):
            warnings.append("Known pitcher handedness mappings unavailable in game-log CSVs; checking local Statcast cache.")

        lookup = PlayerHandednessLookupService(self.settings, season=season, date_label=date_label)
        pitcher_resolver = _OpposingPitcherResolver(self.settings, date_label=date_label, season=season, seed_rows=seed_rows)
        recent_splits = _recent_vs_hand_by_player_team(self.settings, date_label=date_label, season=season)
        statcast_splits, statcast_source = _statcast_split_indexes(self.settings, date_label=date_label, season=season)
        batter_rows_by_player = _batter_rows_by_player_team(all_batter_rows)
        pitcher_avg_allowed = _pitcher_avg_allowed_by_name(all_pitcher_rows)
        generated_at = datetime.now(timezone.utc).isoformat()
        output = [
            _platoon_summary(
                date_label,
                season,
                seed,
                batter_rows_by_player.get((seed["normalizedPlayer"], seed["normalizedTeam"])) or [],
                lookup,
                pitcher_resolver,
                recent_splits,
                statcast_splits,
                pitcher_avg_allowed,
                batter_path if batter_path.is_file() else Path(""),
                generated_at,
            )
            for seed in seed_rows
        ]
        if not output:
            warnings.append("No current board batter context rows generated.")
        for row in output:
            row_warnings = [warning for warning in str(row.get("warnings") or "").split("; ") if warning]
            if not row.get("batter_hand") and "missing batter history" in str(row.get("enrichmentStatus", "")):
                row_warnings.append("batter history unavailable")
            if not row.get("batter_hand"):
                row_warnings.append("batter_hand unknown")
            if not row.get("pitcher_hand"):
                row_warnings.append("pitcher_hand unknown")
            if not _has_any_split_stat(row):
                row_warnings.append("split stats unavailable")
            row["warnings"] = "; ".join(row_warnings)
        write_csv_rows(output_path, output, HAND_PLATOON_FIELDS)
        diagnostics = self._diagnostics(date_label, season, seed_diagnostics, output, seed_rows)
        diagnostics["splitStatsSource"] = statcast_source or (str(batter_path) if batter_path.is_file() else "")
        diagnostics["recentSplitSource"] = str(self.settings.data_dir / "cache" / "incremental_stats" / f"batter_recent_vs_hand_{season}.csv")
        diagnostics["pitcherSplitSource"] = statcast_source or (str(pitcher_path) if pitcher_path.is_file() else "")
        diagnostics["recentSplitWindow"] = "latest pregame row from 30-day batter_recent_vs_hand cache"
        diagnostics["splitStatsWindow"] = "season-to-date rows before target date"
        diagnostics["splitStatsRowsUsed"] = int(statcast_splits.get("rowsUsed") or 0)
        diagnostics["recentSplitRowsUsed"] = int(recent_splits.get("rowsUsed") or 0)
        diagnostics["pitcherSplitRowsUsed"] = int(statcast_splits.get("pitcherRowsUsed") or 0)
        return self._result(status_for_rows(len(output), warnings), date_label, season, len(output), output_path, warnings, diagnostics)

    def _batter_log_path(self, season: int) -> Path:
        cloud = self.settings.data_dir / "cloud" / "season_logs" / f"batter_game_logs_{season}.csv"
        warehouse = self.settings.data_dir / "warehouse" / "season_logs" / f"batter_game_logs_{season}.csv"
        return warehouse if warehouse.is_file() else cloud

    def _pitcher_log_path(self, season: int) -> Path:
        cloud = self.settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        warehouse = self.settings.data_dir / "warehouse" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        return warehouse if warehouse.is_file() else cloud

    def _seed_rows(self, *, date_label: str, season: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        seed_path = self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv"
        source_mode = "playerboard"
        raw_rows = _read_date_rows(seed_path, date_label)
        if not raw_rows:
            seed_path = self.settings.data_dir / "odds" / f"propline_props_{date_label}.csv"
            source_mode = "propline_props"
            raw_rows = _read_date_rows(seed_path, date_label, date_aliases=("eventDateLocal", "date"))

        diagnostics: dict[str, Any] = {
            "providerSourceMode": source_mode if raw_rows else "none",
            "providerSeedPath": str(seed_path),
            "providerSeedRows": len(raw_rows),
            "providerSeedDate": date_label,
            "providerSeedSlateMatchesTargetDate": bool(raw_rows),
            "boardSeedRows": len(raw_rows) if source_mode == "playerboard" else 0,
            "boardSeedBatterRows": 0,
            "boardSeedPitcherRows": 0,
            "boardSeedSkippedRows": 0,
            "boardSeedSkipReasons": {},
            "contextRowsUsingCorrectedAttribution": 0,
            "contextRowsSkippedByAttributionConflict": 0,
            "sampleCorrectedContextJoinKeys": [],
            "sampleBlockedContextJoinKeys": [],
            "sampleContextRowsBeforeAfterCorrection": [],
        }
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        skip_reasons: defaultdict[str, int] = defaultdict(int)
        batter_rows = 0
        pitcher_rows = 0
        for raw in raw_rows:
            attributed = apply_attribution(raw)
            aligned = align_board_context_identity(attributed)
            status = clean(aligned.get("attributionStatus")).lower()
            before_key = _raw_context_key(raw, aligned, date_label, season)
            after_key = _context_key(aligned, date_label, season)
            if aligned.get("attributionCorrectionApplied") and not aligned.get("contextBlockedByAttribution"):
                diagnostics["contextRowsUsingCorrectedAttribution"] = int(diagnostics["contextRowsUsingCorrectedAttribution"]) + 1
                _add_sample(diagnostics["sampleCorrectedContextJoinKeys"], after_key)
                _add_sample(
                    diagnostics["sampleContextRowsBeforeAfterCorrection"],
                    {
                        "player": clean(aligned.get("subjectName")) or clean(aligned.get("player")),
                        "beforeKey": before_key,
                        "afterKey": after_key,
                        "beforeTeam": clean(first_value(raw, ["originalTeam", "sourceTeam", "team", "teamAbbr"])),
                        "beforeOpponent": clean(first_value(raw, ["originalOpponent", "sourceOpponent", "opponent", "opponentAbbr"])),
                        "afterTeam": clean(first_value(aligned, ["resolvedTeam", "team"])),
                        "afterOpponent": clean(first_value(aligned, ["resolvedOpponent", "opponent"])),
                        "attributionStatus": status,
                    },
                )
            if status in {"conflict", "ambiguous", "invalid_player_label"} or aligned.get("contextBlockedByAttribution"):
                diagnostics["contextRowsSkippedByAttributionConflict"] = int(diagnostics["contextRowsSkippedByAttributionConflict"]) + 1
                skip_reasons[f"attribution_{status or 'blocked'}"] += 1
                _add_sample(diagnostics["sampleBlockedContextJoinKeys"], after_key)
                continue
            role = clean(aligned.get("subjectRole")).lower() or "unknown"
            if role == "pitcher":
                pitcher_rows += 1
                skip_reasons["role_not_applicable"] += 1
                continue
            if role != "batter":
                skip_reasons["role_not_batter"] += 1
                continue
            batter_rows += 1
            player = clean(aligned.get("subjectName"))
            normalized_player = clean(aligned.get("normalizedSubjectName")) or normalize_player_name(player)
            team = clean(aligned.get("subjectTeam"))
            opponent = clean(aligned.get("subjectOpponent"))
            normalized_team = clean(aligned.get("normalizedSubjectTeam")) or normalize_team(team)
            normalized_opponent = clean(aligned.get("normalizedSubjectOpponent")) or normalize_opponent(opponent)
            if not normalized_player:
                skip_reasons["missing_subject_identity"] += 1
                continue
            if not normalized_team:
                skip_reasons["missing_subject_team"] += 1
                continue
            if not normalized_opponent:
                skip_reasons["missing_subject_opponent"] += 1
                continue
            display_team = (
                clean(first_value(aligned, ["correctedTeam", "resolvedTeam"]))
                if aligned.get("attributionCorrectionApplied")
                else team
            )
            display_opponent = (
                clean(first_value(aligned, ["correctedOpponent", "resolvedOpponent"]))
                if aligned.get("attributionCorrectionApplied")
                else opponent
            )
            seed_key = (normalized_player, normalized_team, normalized_opponent)
            seed = deduped.setdefault(
                seed_key,
                {
                    "player": player,
                    "team": display_team or team or normalized_team,
                    "opponent": display_opponent or opponent or normalized_opponent,
                    "normalizedPlayer": normalized_player,
                    "normalizedTeam": normalized_team,
                    "normalizedOpponent": normalized_opponent,
                    "subjectRole": "batter",
                    "pitcher": clean(first_value(aligned, ["pitcher", "probablePitcher", "probable_pitcher"])),
                    "seedSource": source_mode,
                    "seedMarketCount": 0,
                    "seedRowCount": 0,
                    "seedSubjectNameSource": clean(aligned.get("subjectNameSource")),
                },
            )
            seed["seedMarketCount"] = len(
                set(
                    str(value).strip()
                    for value in [seed.get("markets", ""), clean(first_value(aligned, ["market", "baseMarket"]))]
                    if str(value).strip()
                )
            )
            seed["seedRowCount"] = int(seed.get("seedRowCount") or 0) + 1
            market = clean(first_value(aligned, ["market", "baseMarket"]))
            if market:
                markets = set(str(seed.get("markets") or "").split("|")) if seed.get("markets") else set()
                markets.add(market)
                seed["markets"] = "|".join(sorted(markets))
                seed["seedMarketCount"] = len(markets)

        diagnostics["providerSeedBatterRows"] = batter_rows
        diagnostics["providerSeedPitcherRows"] = pitcher_rows
        diagnostics["boardSeedBatterRows"] = batter_rows if source_mode == "playerboard" else 0
        diagnostics["boardSeedPitcherRows"] = pitcher_rows if source_mode == "playerboard" else 0
        diagnostics["boardSeedSkippedRows"] = sum(skip_reasons.values())
        diagnostics["boardSeedSkipReasons"] = dict(sorted(skip_reasons.items()))
        diagnostics["contextRowsDeduped"] = max(batter_rows - len(deduped), 0)
        return list(deduped.values()), diagnostics

    def _diagnostics(
        self,
        date_label: str,
        season: int,
        seed_diagnostics: dict[str, Any],
        output: list[dict[str, Any]],
        seed_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        seed_keys = {_context_key(seed, date_label, season) for seed in seed_rows}
        output_keys = {_context_key(row, date_label, season) for row in output}
        not_on_board = [row for row in output if _context_key(row, date_label, season) not in seed_keys]
        without_context = [seed for seed in seed_rows if _context_key(seed, date_label, season) not in output_keys]
        with_split_stats = [row for row in output if _has_any_split_stat(row)]
        resolved_pitchers = [row for row in output if clean(row.get("opposingPitcher"))]
        ambiguous_pitchers = [row for row in output if "ambiguous_opposing_pitcher" in str(row.get("warnings") or "")]
        missing_pitchers = [row for row in output if not clean(row.get("opposingPitcher")) and row not in ambiguous_pitchers]
        diagnostics = {
            **seed_diagnostics,
            "contextRowsGenerated": len(output),
            "contextRowsGeneratedFromBoard": len(output) if seed_diagnostics.get("providerSourceMode") == "playerboard" else 0,
            "contextRowsMatchingBoardSubjects": len(output_keys.intersection(seed_keys)),
            "contextRowsNotOnBoardSlate": len(not_on_board),
            "boardBatterSubjectsWithoutContextRows": len(without_context),
            "contextRowsWithBatterHand": sum(1 for row in output if clean(row.get("batter_hand"))),
            "contextRowsWithPitcherHand": sum(1 for row in output if clean(row.get("pitcher_hand"))),
            "contextRowsWithSplitStats": len(with_split_stats),
            "contextRowsWithRecentHitsVsLhp": sum(1 for row in output if clean(row.get("batter_recent_hits_vs_lhp"))),
            "contextRowsWithRecentHitsVsRhp": sum(1 for row in output if clean(row.get("batter_recent_hits_vs_rhp"))),
            "contextRowsWithPitcherAvgAllowedVsHand": sum(1 for row in output if clean(row.get("pitcher_avg_allowed_vs_hand"))),
            "batterHandSourceCounts": dict(
                Counter(clean(row.get("source")) for row in output if clean(row.get("batter_hand")) and clean(row.get("source")))
            ),
            "pitcherHandSourceCounts": dict(
                Counter(clean(row.get("source")) for row in output if clean(row.get("pitcher_hand")) and clean(row.get("source")))
            ),
            "opposingPitcherRowsResolved": len(resolved_pitchers),
            "opposingPitcherRowsMissing": len(missing_pitchers),
            "opposingPitcherRowsAmbiguous": len(ambiguous_pitchers),
            "externalApiCallsMade": 0,
            "pregameSafe": True,
            "labelsExcluded": True,
            "warnings": sorted({warning for row in output for warning in str(row.get("warnings") or "").split("; ") if warning}),
            "sampleBoardBatterWithoutContext": [_sample(seed) for seed in without_context[:10]],
            "sampleContextNotOnBoard": [_sample(row) for row in not_on_board[:10]],
            "sampleRowsMissingHandedness": [_sample(row) for row in output if not clean(row.get("batter_hand"))][:10],
            "sampleRowsMissingBatterHand": [_sample(row) for row in output if not clean(row.get("batter_hand"))][:10],
            "sampleRowsMissingPitcherHand": [_sample(row) for row in output if not clean(row.get("pitcher_hand"))][:10],
            "sampleRowsMissingRecentSplits": [
                _sample(row)
                for row in output
                if not clean(row.get("batter_recent_hits_vs_lhp")) and not clean(row.get("batter_recent_hits_vs_rhp"))
            ][:10],
            "sampleRowsMissingPitcherSplits": [_sample(row) for row in output if not clean(row.get("pitcher_avg_allowed_vs_hand"))][:10],
            "sampleResolvedOpposingPitchers": [_sample(row) for row in resolved_pitchers[:10]],
            "sampleMissingOpposingPitchers": [_sample(row) for row in missing_pitchers[:10]],
            "sampleAmbiguousOpposingPitchers": [_sample(row) for row in ambiguous_pitchers[:10]],
            "ambiguousBatterHandRows": [_sample(row) for row in output if "ambiguous_batter" in str(row.get("warnings") or "")][:10],
            "ambiguousPitcherHandRows": [_sample(row) for row in output if "ambiguous_pitcher" in str(row.get("warnings") or "")][:10],
        }
        diagnostics["boardBatterRowsWithoutContext"] = diagnostics["boardBatterSubjectsWithoutContextRows"]
        diagnostics["contextRowsNotOnBoard"] = diagnostics["contextRowsNotOnBoardSlate"]
        return diagnostics

    def _result(
        self,
        status: str,
        date_label: str,
        season: int,
        rows: int,
        path: Path,
        warnings: list[str],
        diagnostics: dict[str, Any],
    ) -> ContextProviderResult:
        return ContextProviderResult(
            status=status,
            date=date_label,
            season=season,
            source="handedness_platoon",
            rows=rows,
            path=str(path),
            warnings=warnings,
            diagnostics=diagnostics,
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


def _batter_rows_by_player_team(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        player = clean(first_value(row, ["player", "playerName", "name"]))
        team = clean(first_value(row, ["team", "teamAbbr"]))
        normalized_player = normalize_player_name(player)
        normalized_team = normalize_team(team)
        if normalized_player and normalized_team:
            grouped[(normalized_player, normalized_team)].append(row)
    return {group_key: sorted(value, key=lambda row: clean(first_value(row, ["date", "game_date", "gameDate"]))) for group_key, value in grouped.items()}


def clean_subject_name_for_pitcher_row(value: Any) -> str:
    cleaned, _ = clean_subject_name(value, "pitcher_strikeouts")
    return cleaned


class _OpposingPitcherResolver:
    def __init__(self, settings: Settings, *, date_label: str, season: int, seed_rows: list[dict[str, Any]]) -> None:
        self.settings = settings
        self.date_label = date_label
        self.season = season
        self.board_pitchers = self._board_pitchers(seed_rows)
        self.schedule_pitchers = self._schedule_pitchers()

    def resolve(self, seed: dict[str, Any]) -> dict[str, Any]:
        team = normalize_team(seed.get("team") or seed.get("normalizedTeam"))
        opponent = normalize_team(seed.get("opponent") or seed.get("normalizedOpponent"))
        explicit = clean(seed.get("pitcher"))
        if explicit:
            return {
                "opposingPitcher": explicit,
                "opposingPitcherTeam": opponent,
                "source": "board_pitcher_field",
                "warnings": [],
            }
        candidates = []
        if team and opponent:
            candidates.extend(self.schedule_pitchers.get((opponent, team), []))
            candidates.extend(self.board_pitchers.get((opponent, team), []))
        names = {normalize_player_name(candidate.get("name")) for candidate in candidates if normalize_player_name(candidate.get("name"))}
        if len(names) == 1:
            candidate = candidates[0]
            return {
                "opposingPitcher": clean(candidate.get("name")),
                "opposingPitcherTeam": clean(candidate.get("team")) or opponent,
                "source": clean(candidate.get("source")),
                "warnings": [],
            }
        if len(names) > 1:
            return {"opposingPitcher": "", "opposingPitcherTeam": opponent, "source": "", "warnings": ["ambiguous_opposing_pitcher"]}
        return {"opposingPitcher": "", "opposingPitcherTeam": opponent, "source": "", "warnings": ["opposing_pitcher_not_found"]}

    def _board_pitchers(self, seed_rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, str]]]:
        grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        sources = [
            (
                self.settings.data_dir / "playerboard" / f"playerboard_{self.season}.csv",
                ("date", "game_date", "gameDate", "event_date"),
                "playerboard_pitcher_rows",
            ),
            (
                self.settings.data_dir / "odds" / f"propline_props_{self.date_label}.csv",
                ("eventDateLocal", "date"),
                "propline_pitcher_rows",
            ),
        ]
        for path, date_aliases, source in sources:
            for raw in _read_date_rows(path, self.date_label, date_aliases=date_aliases):
                row = align_board_context_identity(apply_attribution(raw))
                status = clean(row.get("attributionStatus")).lower()
                if status in {"conflict", "ambiguous", "invalid_player_label"} or row.get("contextBlockedByAttribution"):
                    continue
                if clean(row.get("subjectRole")).lower() != "pitcher":
                    continue
                name = clean(raw.get("subjectName")) or clean(raw.get("player")) or clean(row.get("subjectName"))
                name = clean_subject_name_for_pitcher_row(name)
                team = normalize_team(row.get("subjectTeam") or row.get("team"))
                opponent = normalize_team(row.get("subjectOpponent") or row.get("opponent"))
                if name and team and opponent:
                    grouped[(team, opponent)].append({"name": name, "team": team, "source": source})
        return grouped

    def _schedule_pitchers(self) -> dict[tuple[str, str], list[dict[str, str]]]:
        path = self.settings.data_dir / "cache" / "incremental_stats" / f"games_{self.season}.csv"
        grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in read_csv_rows(path):
            if clean(row.get("date"))[:10] != self.date_label:
                continue
            away = normalize_team(row.get("away"))
            home = normalize_team(row.get("home"))
            away_pitcher = clean(row.get("awayProbablePitcher"))
            home_pitcher = clean(row.get("homeProbablePitcher"))
            if away and home and away_pitcher:
                grouped[(away, home)].append({"name": away_pitcher, "team": away, "source": str(path)})
            if away and home and home_pitcher:
                grouped[(home, away)].append({"name": home_pitcher, "team": home, "source": str(path)})
        return grouped


def _recent_vs_hand_by_player_team(settings: Settings, *, date_label: str, season: int) -> dict[str, Any]:
    path = settings.data_dir / "cache" / "incremental_stats" / f"batter_recent_vs_hand_{season}.csv"
    rows = _pregame_rows(read_csv_rows(path), date_label) if path.is_file() else []
    latest: dict[tuple[str, str], dict[str, str]] = {}
    latest_by_id: dict[str, dict[str, str]] = {}
    for row in sorted(rows, key=lambda item: clean(item.get("date"))):
        player = normalize_player_name(row.get("player"))
        team = normalize_team(row.get("team"))
        player_id = clean(row.get("playerId"))
        if player and team:
            latest[(player, team)] = row
        if player_id:
            latest_by_id[player_id] = row
    return {"byNameTeam": latest, "byId": latest_by_id, "rowsUsed": len(rows), "path": str(path)}


def _lookup_recent_split(recent_splits: dict[str, Any], *, player_name: str, team: str, player_id: str) -> dict[str, str]:
    if player_id:
        row = (recent_splits.get("byId") or {}).get(player_id)
        if row:
            return row
    return (recent_splits.get("byNameTeam") or {}).get((normalize_player_name(player_name), normalize_team(team)), {}) or {}


def _statcast_split_indexes(settings: Settings, *, date_label: str, season: int) -> tuple[dict[str, Any], str]:
    paths = [
        settings.data_dir / "warehouse" / "statcast" / f"statcast_{season}.csv",
        settings.data_dir / "cache" / "statcast" / f"statcast_{season}.csv",
        *sorted((settings.data_dir / "cache" / "savant").glob(f"statcast_{season}_*.csv")),
        *sorted((settings.data_dir / "cache" / "savant" / "raw").glob(f"statcast_{season}_*.csv")),
    ]
    player_index = _player_index_by_id(settings, season)
    batter_grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    pitcher_grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    source = ""
    rows_used = 0
    pitcher_rows_used = 0
    for path in paths:
        if not path.is_file():
            continue
        rows = _pregame_rows(read_csv_rows(path), date_label)
        if not rows:
            continue
        source = str(path)
        for row in rows:
            event = clean(row.get("events"))
            if not event:
                continue
            pitcher_hand = _normalized_hand(first_value(row, ["p_throws", "throws", "pitcher_hand"]))
            batter_hand = _normalized_hand(first_value(row, ["stand", "batter_hand"]))
            batter_id = clean(first_value(row, ["batter", "batter_id", "player_mlbam_id"]))
            meta = player_index.get(batter_id, {})
            batter_name = normalize_player_name(first_value(row, ["batter_name", "player", "name"]) or meta.get("player", ""))
            batter_team = normalize_team(_statcast_batter_team(row) or meta.get("team", ""))
            pitcher_name = normalize_player_name(_normal_name(clean(first_value(row, ["player_name", "pitcher_name", "pitcherPlayerName"]))))
            if batter_name and pitcher_hand:
                batter_grouped[(batter_id, batter_name, batter_team, pitcher_hand)].append(row)
                rows_used += 1
            if pitcher_name and batter_hand:
                pitcher_grouped[(pitcher_name, batter_hand)].append(row)
                pitcher_rows_used += 1
        break
    batter_splits = {key: {**_pa_rates(rows), "source": source} for key, rows in batter_grouped.items()}
    pitcher_splits = {key: {"avgAllowed": _pa_rates(rows).get("avg", ""), "source": source} for key, rows in pitcher_grouped.items()}
    return {"batterSplits": batter_splits, "pitcherSplits": pitcher_splits, "rowsUsed": rows_used, "pitcherRowsUsed": pitcher_rows_used}, source


def _statcast_batter_key(
    statcast_splits: dict[str, Any],
    *,
    player_name: str,
    team: str,
    player_id: str,
    pitcher_hand: str,
) -> tuple[str, str, str, str] | None:
    if not pitcher_hand:
        return None
    splits = statcast_splits.get("batterSplits") or {}
    normalized_name = normalize_player_name(player_name)
    normalized_team = normalize_team(team)
    candidates = [
        key
        for key in splits
        if key[3] == pitcher_hand
        and ((player_id and key[0] == player_id) or (key[1] == normalized_name and (not normalized_team or key[2] == normalized_team)))
    ]
    return candidates[0] if len(candidates) == 1 else None


def _pa_rates(rows: list[dict[str, str]]) -> dict[str, float | str]:
    pa_rows = [row for row in rows if clean(row.get("events"))]
    at_bats = [row for row in pa_rows if clean(row.get("events")).lower() not in {"walk", "hit_by_pitch", "sac_bunt", "sac_fly", "catcher_interf"}]
    hits = [row for row in at_bats if clean(row.get("events")).lower() in {"single", "double", "triple", "home_run"}]
    strikeouts = [row for row in pa_rows if clean(row.get("events")).lower() == "strikeout"]
    return {"avg": _rate(len(hits), len(at_bats)), "kRate": _rate(len(strikeouts), len(pa_rows))}


def _rate(numerator: float, denominator: float) -> float | str:
    if denominator <= 0:
        return ""
    return round(float(numerator) / float(denominator), 6)


def _player_index_by_id(settings: Settings, season: int) -> dict[str, dict[str, str]]:
    path = settings.data_dir / "cache" / "incremental_stats" / f"player_index_{season}.csv"
    return {clean(row.get("playerId")): row for row in read_csv_rows(path) if clean(row.get("playerId"))}


def _statcast_batter_team(row: dict[str, Any]) -> str:
    half = clean(first_value(row, ["inning_topbot"])).lower()
    if half.startswith("top"):
        return clean(first_value(row, ["away_team", "awayTeam"]))
    if half.startswith("bot"):
        return clean(first_value(row, ["home_team", "homeTeam"]))
    return clean(first_value(row, ["team", "bat_team", "batting_team"]))


def _normal_name(value: str) -> str:
    if "," in value:
        last, first = [part.strip() for part in value.split(",", 1)]
        return f"{first} {last}".strip()
    return value


def _first_source(values: list[Any]) -> str:
    for value in values:
        text = clean(value)
        if text:
            return text
    return ""


def _platoon_summary(
    date_label: str,
    season: int,
    seed: dict[str, Any],
    rows: list[dict[str, str]],
    lookup: PlayerHandednessLookupService,
    pitcher_resolver: "_OpposingPitcherResolver",
    recent_splits: dict[str, Any],
    statcast_splits: dict[str, Any],
    pitcher_avg_allowed: dict[tuple[str, str], float | str],
    source: Path,
    generated_at: str,
) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    player = clean(seed.get("player"))
    team = clean(seed.get("team"))
    opponent = clean(seed.get("opponent"))
    batter_id = clean(first_value(latest, ["playerId", "player_mlbam_id"])) if latest else clean(seed.get("playerId"))
    pitcher_resolution = pitcher_resolver.resolve(seed)
    pitcher_name = pitcher_resolution.get("opposingPitcher") or clean(seed.get("pitcher"))
    normalized_pitcher = normalize_player_name(pitcher_name)
    batter_lookup = lookup.lookup(role="batter", player_id=batter_id, player_name=player, team=team)
    batter_hand = batter_lookup.batter_hand
    pitcher_lookup = lookup.lookup(
        role="pitcher",
        player_name=pitcher_name,
        team=pitcher_resolution.get("opposingPitcherTeam") or opponent,
    )
    pitcher_hand = pitcher_lookup.pitcher_hand
    split_rows = [row for row in rows if _normalized_hand(first_value(row, ["pitcher_hand", "p_throws", "throws"])) == pitcher_hand]
    recent = _lookup_recent_split(recent_splits, player_name=player, team=team, player_id=batter_id)
    statcast_batter_key = _statcast_batter_key(statcast_splits, player_name=player, team=team, player_id=batter_id, pitcher_hand=pitcher_hand)
    statcast_batter_split = (statcast_splits.get("batterSplits") or {}).get(statcast_batter_key, {}) if statcast_batter_key else {}
    statcast_pitcher_split = (statcast_splits.get("pitcherSplits") or {}).get((normalized_pitcher, batter_hand), {})
    enrichment_status = []
    if not rows:
        enrichment_status.append("missing batter history")
    if not batter_hand:
        enrichment_status.append("missing batter_hand")
    if not pitcher_hand:
        enrichment_status.append("missing pitcher_hand")
    if not pitcher_resolution.get("opposingPitcher"):
        enrichment_status.append("missing opposing_pitcher")
    return {
        "date": date_label,
        "season": season,
        "player": player,
        "team": team,
        "opponent": opponent,
        "normalizedPlayer": clean(seed.get("normalizedPlayer")) or normalize_player_name(player),
        "normalizedTeam": clean(seed.get("normalizedTeam")) or normalize_team(team),
        "normalizedOpponent": clean(seed.get("normalizedOpponent")) or normalize_opponent(opponent),
        "subjectRole": "batter",
        "opposingPitcher": pitcher_resolution.get("opposingPitcher", ""),
        "normalizedOpposingPitcher": normalized_pitcher,
        "opposingPitcherTeam": pitcher_resolution.get("opposingPitcherTeam", ""),
        "batter_hand": batter_hand,
        "pitcher_hand": pitcher_hand,
        "batter_avg_vs_hand": statcast_batter_split.get("avg", "") or _avg(split_rows),
        "batter_k_rate_vs_hand": statcast_batter_split.get("kRate", "") or _k_rate(split_rows),
        "batter_recent_hits_vs_lhp": recent.get("batter_recent_hits_vs_lhp", ""),
        "batter_recent_hits_vs_rhp": recent.get("batter_recent_hits_vs_rhp", ""),
        "pitcher_avg_allowed_vs_hand": statcast_pitcher_split.get("avgAllowed", "")
        or pitcher_avg_allowed.get((normalized_pitcher, batter_hand), ""),
        "source": _first_source([batter_lookup.source, pitcher_lookup.source, statcast_batter_split.get("source"), str(source)]),
        "sourceUpdatedAt": _first_source([batter_lookup.sourceUpdatedAt, pitcher_lookup.sourceUpdatedAt, _source_updated_at(source)]),
        "generatedAt": generated_at,
        "pregameSafe": True,
        "labelsExcluded": True,
        "warnings": "; ".join(
            [
                *batter_lookup.warnings,
                *pitcher_lookup.warnings,
                *list(pitcher_resolution.get("warnings") or []),
            ]
        ),
        "seedSource": seed.get("seedSource", ""),
        "seedMarketCount": seed.get("seedMarketCount", ""),
        "seedRowCount": seed.get("seedRowCount", ""),
        "seedSubjectNameSource": seed.get("seedSubjectNameSource", ""),
        "enrichmentStatus": "; ".join(enrichment_status) or "partial",
    }


def _latest_pitcher_hand_by_name(rows: list[dict[str, str]]) -> dict[str, str]:
    hands: dict[str, str] = {}
    for row in rows:
        pitcher = normalize_player_name(first_value(row, ["player", "playerName", "pitcher", "name"]))
        hand = _normalized_hand(first_value(row, ["throws", "p_throws", "pitcher_hand"]))
        if pitcher and hand:
            hands[pitcher] = hand
    return hands


def _pitcher_avg_allowed_by_name(rows: list[dict[str, str]]) -> dict[tuple[str, str], float | str]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        pitcher = normalize_player_name(first_value(row, ["player", "playerName", "pitcher", "name"]))
        hand = _normalized_hand(first_value(row, ["batter_hand", "stand"]))
        if pitcher and hand:
            grouped[(pitcher, hand)].append(row)
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


def _read_date_rows(path: Path, date_label: str, date_aliases: tuple[str, ...] = ("date", "game_date", "gameDate", "event_date")) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_date = clean(first_value(row, list(date_aliases)))
            if raw_date[:10] == date_label:
                rows.append(dict(row))
    return rows


def _has_any_split_stat(row: dict[str, Any]) -> bool:
    for field in (
        "batter_avg_vs_hand",
        "batter_k_rate_vs_hand",
        "batter_recent_hits_vs_lhp",
        "batter_recent_hits_vs_rhp",
        "pitcher_avg_allowed_vs_hand",
    ):
        if clean(row.get(field)):
            return True
    return False


def _context_key(row: dict[str, Any], date_label: str, season: int) -> str:
    return "|".join(
        [
            date_label,
            str(season),
            clean(row.get("normalizedPlayer")) or normalize_player_name(row.get("player")),
            clean(row.get("normalizedTeam")) or normalize_team(row.get("team")),
            clean(row.get("normalizedOpponent")) or normalize_opponent(row.get("opponent")),
        ]
    )


def _raw_context_key(raw: dict[str, Any], aligned: dict[str, Any], date_label: str, season: int) -> str:
    return "|".join(
        [
            date_label,
            str(season),
            normalize_player_name(
                first_value(
                    raw,
                    ["rawPlayerName", "sourcePlayerLabel", "subjectName", "player", "playerName", "name"],
                    first_value(aligned, ["subjectName", "player"], ""),
                )
            ),
            normalize_team(first_value(raw, ["originalTeam", "sourceTeam", "team", "teamAbbr", "team_abbr"], "")),
            normalize_opponent(
                first_value(raw, ["originalOpponent", "sourceOpponent", "opponent", "opponentAbbr", "opponent_abbr"], "")
            ),
        ]
    )


def _add_sample(samples: list[Any], sample: Any, *, limit: int = 10) -> None:
    if sample in samples:
        return
    if len(samples) < limit:
        samples.append(sample)


def _sample(row: dict[str, Any]) -> dict[str, str]:
    return {
        "player": clean(row.get("player")),
        "team": clean(row.get("team")),
        "opponent": clean(row.get("opponent")),
        "normalizedPlayer": clean(row.get("normalizedPlayer")),
        "normalizedTeam": clean(row.get("normalizedTeam")),
        "normalizedOpponent": clean(row.get("normalizedOpponent")),
    }
