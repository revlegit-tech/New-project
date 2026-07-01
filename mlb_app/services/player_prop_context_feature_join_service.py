from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.player_prop_context_identity_service import (
    align_board_context_identity,
    normalize_book_key,
    normalize_opponent,
    normalize_player_name,
    normalize_team,
)
from mlb_app.services.player_prop_identity_confidence import identity_confidence_for_row
from mlb_app.services.player_prop_model_runtime import first_value, model_market_key, to_float
from mlb_app.services.prop_side_normalization import normalize_prop_side


@dataclass(frozen=True)
class ContextArtifactSpec:
    group: str
    folder: str
    filename_template: str
    join_fields: tuple[str, ...] = ()


@dataclass
class ContextJoinResult:
    rows: list[dict[str, Any]]
    artifacts: dict[str, dict[str, Any]]
    counts: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    board_alignment_diagnostics: dict[str, Any] = field(default_factory=dict)


CONTEXT_ARTIFACTS = (
    ContextArtifactSpec("odds_movement", "odds_movement", "odds_movement_{date}.csv", ("odds_move", "line_move")),
    ContextArtifactSpec(
        "player_recent_form",
        "player_recent_form",
        "player_recent_form_{date}.csv",
        (
            "recent_games",
            "recent_rate",
            "season_rate",
            "rolling_avg_5",
            "rolling_avg_10",
            "rolling_avg_15",
            "rolling_total_bases_10",
            "rolling_hr_rate_15",
            "rolling_k_rate_10",
        ),
    ),
    ContextArtifactSpec(
        "pitcher_context",
        "pitcher_context",
        "pitcher_context_{date}.csv",
        (
            "pitcher_recent_games",
            "pitcher_k_rate",
            "pitcher_walk_rate",
            "pitcher_hr_rate",
            "pitcher_babip",
            "pitcher_days_rest",
            "pitcher_velo_delta",
        ),
    ),
    ContextArtifactSpec("game_markets", "game_markets", "game_markets_{date}.csv"),
    ContextArtifactSpec("weather", "weather", "weather_context_{date}.csv"),
    ContextArtifactSpec(
        "statcast",
        "statcast",
        "statcast_context_{date}.csv",
        (
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
        ),
    ),
    ContextArtifactSpec(
        "handedness_platoon",
        "handedness_platoon",
        "handedness_platoon_{date}.csv",
        (
            "batter_hand",
            "pitcher_hand",
            "batter_avg_vs_hand",
            "batter_k_rate_vs_hand",
            "batter_recent_hits_vs_lhp",
            "batter_recent_hits_vs_rhp",
            "pitcher_avg_allowed_vs_hand",
        ),
    ),
    ContextArtifactSpec("bullpen_context", "bullpen", "bullpen_context_{date}.csv"),
    ContextArtifactSpec("umpire", "umpire", "umpire_context_{date}.csv"),
)


class PlayerPropContextFeatureJoinService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def join(
        self,
        rows: list[dict[str, Any]],
        *,
        date_label: str,
        season: int,
        input_source: str,
    ) -> ContextJoinResult:
        output = [align_board_context_identity(row) for row in rows]
        artifacts = self.load_artifacts(date_label=date_label)
        warnings: list[str] = []
        board_alignment_diagnostics = _board_alignment_diagnostics(output)
        diagnostics = _new_diagnostics(artifacts)
        counts: dict[str, Any] = {
            "oddsMovementRowsLoaded": artifacts["odds_movement"]["rows"],
            "oddsMovementRowsJoined": 0,
            "oddsMovementRowsSkipped": 0,
            "oddsMovementAmbiguousRows": 0,
            "playerRecentFormRowsLoaded": artifacts["player_recent_form"]["rows"],
            "playerRecentFormRowsJoined": 0,
            "playerRecentFormRowsSkipped": 0,
            "playerRecentFormAmbiguousRows": 0,
            "pitcherContextRowsLoaded": artifacts["pitcher_context"]["rows"],
            "pitcherContextRowsJoined": 0,
            "pitcherContextRowsSkipped": 0,
            "pitcherContextAmbiguousRows": 0,
            "statcastRowsLoaded": artifacts["statcast"]["rows"],
            "statcastRowsJoined": 0,
            "statcastRowsSkipped": 0,
            "statcastAmbiguousRows": 0,
            "handednessPlatoonRowsLoaded": artifacts["handedness_platoon"]["rows"],
            "handednessPlatoonRowsJoined": 0,
            "handednessPlatoonRowsSkipped": 0,
            "handednessPlatoonAmbiguousRows": 0,
            "loadedByGroup": {group: int(payload.get("rows") or 0) for group, payload in artifacts.items()},
            "joinedByGroup": {
                "odds_movement": 0,
                "player_recent_form": 0,
                "pitcher_context": 0,
                "statcast": 0,
                "handedness_platoon": 0,
            },
            "skippedByReason": {},
        }
        for group, payload in artifacts.items():
            if not payload.get("exists"):
                warnings.append(f"{group} context artifact missing: {payload.get('path')}")
            elif int(payload.get("rows") or 0) == 0:
                warnings.append(f"{group} context artifact loaded with 0 rows.")
            for warning in payload.get("warnings") or []:
                warnings.append(f"{group}: {warning}")

        odds_rows = artifacts["odds_movement"].get("data") or []
        if odds_rows:
            self._join_odds_movement(
                output,
                odds_rows,
                date_label=date_label,
                season=season,
                input_source=input_source,
                counts=counts,
                warnings=warnings,
                diagnostics=diagnostics,
            )
        elif artifacts["odds_movement"].get("exists"):
            counts["oddsMovementRowsSkipped"] = len(output)

        player_form_rows = artifacts["player_recent_form"].get("data") or []
        if player_form_rows:
            self._join_identity_context(
                output,
                player_form_rows,
                spec=_spec_for_group("player_recent_form"),
                date_label=date_label,
                season=season,
                input_source=input_source,
                context_name_aliases=("normalizedPlayer", "normalized_player", "player", "playerName", "name"),
                row_name_aliases=("subjectName", "normalizedSubjectName", "player", "playerName", "name"),
                context_team_aliases=("normalizedTeam", "normalized_team", "team", "teamAbbr", "team_abbr", "teamCode"),
                row_team_aliases=("subjectTeam", "normalizedSubjectTeam", "team", "teamAbbr", "team_abbr", "teamCode"),
                row_opponent_aliases=("subjectOpponent", "normalizedSubjectOpponent", "opponent", "opponentAbbr", "opponent_abbr", "opponentCode"),
                allowed_row_roles=("batter",),
                loaded_key="playerRecentFormRowsLoaded",
                joined_key="playerRecentFormRowsJoined",
                skipped_key="playerRecentFormRowsSkipped",
                ambiguous_key="playerRecentFormAmbiguousRows",
                counts=counts,
                warnings=warnings,
                diagnostics=diagnostics,
            )
        elif artifacts["player_recent_form"].get("exists"):
            counts["playerRecentFormRowsSkipped"] = len(output)

        pitcher_rows = artifacts["pitcher_context"].get("data") or []
        if pitcher_rows:
            self._join_identity_context(
                output,
                pitcher_rows,
                spec=_spec_for_group("pitcher_context"),
                date_label=date_label,
                season=season,
                input_source=input_source,
                context_name_aliases=("normalizedPitcher", "normalizedPlayer", "pitcher", "player", "playerName", "name"),
                row_name_aliases=("subjectName", "normalizedSubjectName", "pitcher", "probablePitcher"),
                context_team_aliases=("normalizedTeam", "team", "teamAbbr", "team_abbr", "teamCode"),
                row_team_aliases=("subjectTeam", "normalizedSubjectTeam", "team", "teamAbbr"),
                row_opponent_aliases=("subjectOpponent", "normalizedSubjectOpponent", "opponent", "opponentAbbr", "opponent_abbr", "opponentCode"),
                allowed_row_roles=("pitcher",),
                loaded_key="pitcherContextRowsLoaded",
                joined_key="pitcherContextRowsJoined",
                skipped_key="pitcherContextRowsSkipped",
                ambiguous_key="pitcherContextAmbiguousRows",
                counts=counts,
                warnings=warnings,
                diagnostics=diagnostics,
            )
        elif artifacts["pitcher_context"].get("exists"):
            counts["pitcherContextRowsSkipped"] = len(output)

        statcast_rows = artifacts["statcast"].get("data") or []
        if statcast_rows:
            self._join_identity_context(
                output,
                statcast_rows,
                spec=_spec_for_group("statcast"),
                date_label=date_label,
                season=season,
                input_source=input_source,
                context_name_aliases=("normalizedPlayer", "normalized_player", "player", "playerName", "name"),
                row_name_aliases=("subjectName", "normalizedSubjectName", "player", "playerName", "name"),
                context_team_aliases=("normalizedTeam", "normalized_team", "team", "teamAbbr", "team_abbr", "teamCode"),
                row_team_aliases=("subjectTeam", "normalizedSubjectTeam", "team", "teamAbbr", "team_abbr", "teamCode"),
                context_opponent_aliases=("normalizedOpponent", "normalized_opponent", "opponent", "opponentAbbr", "opponent_abbr", "opponentCode"),
                row_opponent_aliases=("subjectOpponent", "normalizedSubjectOpponent", "opponent", "opponentAbbr", "opponent_abbr", "opponentCode"),
                allow_missing_side_unique=True,
                allowed_row_roles=("batter",),
                loaded_key="statcastRowsLoaded",
                joined_key="statcastRowsJoined",
                skipped_key="statcastRowsSkipped",
                ambiguous_key="statcastAmbiguousRows",
                counts=counts,
                warnings=warnings,
                diagnostics=diagnostics,
            )
        elif artifacts["statcast"].get("exists"):
            counts["statcastRowsSkipped"] = len(output)

        platoon_rows = artifacts["handedness_platoon"].get("data") or []
        if platoon_rows:
            self._join_identity_context(
                output,
                platoon_rows,
                spec=_spec_for_group("handedness_platoon"),
                date_label=date_label,
                season=season,
                input_source=input_source,
                context_name_aliases=("normalizedPlayer", "normalized_player", "player", "playerName", "name"),
                row_name_aliases=("subjectName", "normalizedSubjectName", "player", "playerName", "name"),
                context_team_aliases=("normalizedTeam", "normalized_team", "team", "teamAbbr", "team_abbr", "teamCode"),
                row_team_aliases=("subjectTeam", "normalizedSubjectTeam", "team", "teamAbbr", "team_abbr", "teamCode"),
                context_opponent_aliases=("normalizedOpponent", "normalized_opponent", "opponent", "opponentAbbr", "opponent_abbr", "opponentCode"),
                row_opponent_aliases=("subjectOpponent", "normalizedSubjectOpponent", "opponent", "opponentAbbr", "opponent_abbr", "opponentCode"),
                allow_missing_side_unique=True,
                allowed_row_roles=("batter",),
                loaded_key="handednessPlatoonRowsLoaded",
                joined_key="handednessPlatoonRowsJoined",
                skipped_key="handednessPlatoonRowsSkipped",
                ambiguous_key="handednessPlatoonAmbiguousRows",
                counts=counts,
                warnings=warnings,
                diagnostics=diagnostics,
            )
        elif artifacts["handedness_platoon"].get("exists"):
            counts["handednessPlatoonRowsSkipped"] = len(output)

        counts["skippedByReason"] = dict(sorted(Counter(counts["skippedByReason"]).items()))
        counts["joinedByGroup"]["odds_movement"] = counts["oddsMovementRowsJoined"]
        counts["joinedByGroup"]["player_recent_form"] = counts["playerRecentFormRowsJoined"]
        counts["joinedByGroup"]["pitcher_context"] = counts["pitcherContextRowsJoined"]
        counts["joinedByGroup"]["statcast"] = counts["statcastRowsJoined"]
        counts["joinedByGroup"]["handedness_platoon"] = counts["handednessPlatoonRowsJoined"]
        if int(artifacts["odds_movement"]["rows"] or 0) > 0 and counts["oddsMovementRowsJoined"] == 0:
            warnings.append("odds_movement context artifact available but no scoring rows joined safely.")
        if int(artifacts["player_recent_form"]["rows"] or 0) > 0 and counts["playerRecentFormRowsJoined"] == 0:
            warnings.append("player_recent_form context artifact available but no scoring rows joined safely.")
        if int(artifacts["pitcher_context"]["rows"] or 0) > 0 and counts["pitcherContextRowsJoined"] == 0:
            warnings.append("pitcher_context context artifact available but no scoring rows joined safely.")
        if int(artifacts["statcast"]["rows"] or 0) > 0 and counts["statcastRowsJoined"] == 0:
            warnings.append("statcast artifact has rows but no scoring rows joined safely.")
        if int(artifacts["handedness_platoon"]["rows"] or 0) > 0 and counts["handednessPlatoonRowsJoined"] == 0:
            warnings.append("handedness_platoon artifact has rows but no scoring rows joined safely.")
        _finalize_diagnostics(diagnostics, counts)
        return ContextJoinResult(
            rows=output,
            artifacts=_public_artifacts(artifacts),
            counts=counts,
            warnings=sorted(set(warnings)),
            diagnostics=diagnostics,
            board_alignment_diagnostics=board_alignment_diagnostics,
        )

    def load_artifacts(self, *, date_label: str) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}
        for spec in CONTEXT_ARTIFACTS:
            path = self.settings.data_dir / "context" / spec.folder / spec.filename_template.format(date=date_label)
            rows: list[dict[str, Any]] = []
            fields: list[str] = []
            warnings: list[str] = []
            exists = path.is_file()
            if exists:
                try:
                    with path.open("r", encoding="utf-8-sig", newline="") as handle:
                        reader = csv.DictReader(handle)
                        fields = [field for field in (reader.fieldnames or []) if field]
                        rows = [dict(row) for row in reader]
                except Exception as error:
                    warnings.append(f"unreadable artifact: {type(error).__name__}: {error}")
                    rows = []
            artifacts[spec.group] = {
                "path": str(path),
                "exists": exists,
                "rows": len(rows),
                "fields": fields,
                "data": rows,
                "warnings": warnings,
            }
        return artifacts

    def _join_odds_movement(
        self,
        rows: list[dict[str, Any]],
        odds_rows: list[dict[str, Any]],
        *,
        date_label: str,
        season: int,
        input_source: str,
        counts: dict[str, Any],
        warnings: list[str],
        diagnostics: dict[str, Any],
    ) -> None:
        context_by_key: dict[str, list[dict[str, Any]]] = {}
        ambiguous_keys: set[str] = set()
        skipped_reasons: Counter[str] = Counter(counts.get("skippedByReason") or {})

        for context_row in odds_rows:
            key, reason = _odds_join_key(context_row, date_label=date_label, season=season, is_context=True)
            if not key:
                skipped_reasons[f"context_{reason}"] += 1
                continue
            context_by_key.setdefault(key, []).append(context_row)
        for key, candidates in context_by_key.items():
            if len(candidates) > 1:
                ambiguous_keys.add(key)
                counts["oddsMovementAmbiguousRows"] += len(candidates)

        for row in rows:
            key, reason = _odds_join_key(row, date_label=date_label, season=season, is_context=False)
            if not key:
                skipped_reasons[reason] += 1
                counts["oddsMovementRowsSkipped"] += 1
                continue
            if _identity_confidence(row, input_source=input_source) not in {"strong", "medium"}:
                skipped_reasons["weak_or_unknown_identity"] += 1
                counts["oddsMovementRowsSkipped"] += 1
                continue
            if key in ambiguous_keys:
                skipped_reasons["ambiguous_match"] += 1
                counts["oddsMovementRowsSkipped"] += 1
                continue
            matches = context_by_key.get(key) or []
            if len(matches) != 1:
                skipped_reasons["no_unique_match"] += 1
                counts["oddsMovementRowsSkipped"] += 1
                continue
            context_row = matches[0]
            joined = False
            for field in ("odds_move", "line_move"):
                value = first_value(context_row, [field, _camel(field)], "")
                if _is_numeric(value):
                    row[field] = _format_number(to_float(value, math.nan), 6)
                    joined = True
            if joined:
                counts["oddsMovementRowsJoined"] += 1
            else:
                skipped_reasons["matched_but_no_numeric_movement_fields"] += 1
                counts["oddsMovementRowsSkipped"] += 1

        if counts["oddsMovementAmbiguousRows"]:
            warnings.append(f"odds_movement skipped {counts['oddsMovementAmbiguousRows']} ambiguous context rows.")
        counts["skippedByReason"] = dict(skipped_reasons)

    def _join_identity_context(
        self,
        rows: list[dict[str, Any]],
        context_rows: list[dict[str, Any]],
        *,
        spec: ContextArtifactSpec,
        date_label: str,
        season: int,
        input_source: str,
        context_name_aliases: tuple[str, ...],
        row_name_aliases: tuple[str, ...],
        context_team_aliases: tuple[str, ...],
        row_team_aliases: tuple[str, ...],
        context_opponent_aliases: tuple[str, ...] = (),
        row_opponent_aliases: tuple[str, ...] = (),
        allow_missing_side_unique: bool = False,
        allowed_row_roles: tuple[str, ...] = (),
        loaded_key: str,
        joined_key: str,
        skipped_key: str,
        ambiguous_key: str,
        counts: dict[str, Any],
        warnings: list[str],
        diagnostics: dict[str, Any],
    ) -> None:
        context_entries: list[dict[str, Any]] = []
        skipped_reasons: Counter[str] = Counter(counts.get("skippedByReason") or {})
        group_diag = diagnostics.setdefault(spec.group, _empty_group_diagnostics())

        for context_row in context_rows:
            entry, reason = _identity_context_entry(
                context_row,
                name_aliases=context_name_aliases,
                team_aliases=context_team_aliases,
                opponent_aliases=context_opponent_aliases,
                date_label=date_label,
                season=season,
                is_context=True,
                group=spec.group,
            )
            if not entry:
                skipped_reasons[f"{spec.group}_context_{reason}"] += 1
                _diagnostic_reason(group_diag, reason)
                _add_sample(group_diag["unmatchedContextSamples"], _sample_from_row(context_row, reason=reason))
                continue
            context_entries.append(entry)
            _add_sample(group_diag["contextJoinKeyExamples"], entry["key"])

        duplicate_counts = Counter(entry["key"] for entry in context_entries)
        duplicate_keys = {key for key, value in duplicate_counts.items() if value > 1}
        if duplicate_keys:
            duplicate_rows = sum(1 for entry in context_entries if entry["key"] in duplicate_keys)
            counts[ambiguous_key] += duplicate_rows
            group_diag["duplicateContextKeyRows"] += duplicate_rows
            group_diag["ambiguousRows"] += duplicate_rows

        for row in rows:
            role = str(first_value(row, ["subjectRole"], "") or "unknown").strip().lower() or "unknown"
            if allowed_row_roles and role not in allowed_row_roles:
                skipped_reasons[f"{spec.group}_role_not_applicable"] += 1
                counts[skipped_key] += 1
                _diagnostic_reason(group_diag, "role_not_applicable")
                _add_sample(group_diag["unmatchedScoringSamples"], _sample_from_row(row, reason="role_not_applicable"))
                continue
            if _identity_confidence(row, input_source=input_source) not in {"strong", "medium"}:
                skipped_reasons[f"{spec.group}_weak_or_unknown_identity"] += 1
                counts[skipped_key] += 1
                group_diag["weakIdentityRows"] += 1
                _diagnostic_reason(group_diag, "weak_or_unknown_identity")
                _add_sample(group_diag["unmatchedScoringSamples"], _sample_from_row(row, reason="weak_or_unknown_identity"))
                continue
            row_entry, reason = _identity_context_entry(
                row,
                name_aliases=row_name_aliases,
                team_aliases=row_team_aliases,
                opponent_aliases=row_opponent_aliases,
                date_label=date_label,
                season=season,
                is_context=False,
                group=spec.group,
            )
            if not row_entry:
                skipped_reasons[f"{spec.group}_{reason}"] += 1
                counts[skipped_key] += 1
                if reason.startswith("missing"):
                    group_diag["missingKeyRows"] += 1
                _diagnostic_reason(group_diag, reason)
                _add_sample(group_diag["unmatchedScoringSamples"], _sample_from_row(row, reason=reason))
                continue
            candidates = [
                entry for entry in context_entries if _entries_match(row_entry, entry)
            ]
            if not allow_missing_side_unique:
                candidates = [entry for entry in candidates if _entries_have_required_sides(row_entry, entry)]
            if any(entry["key"] in duplicate_keys for entry in candidates) or len(candidates) > 1:
                skipped_reasons[f"{spec.group}_ambiguous_match"] += 1
                counts[skipped_key] += 1
                group_diag["ambiguousRows"] += 1
                _diagnostic_reason(group_diag, "ambiguous_match")
                _add_sample(group_diag["unmatchedScoringSamples"], _sample_from_row(row, reason="ambiguous_match", key=row_entry["key"]))
                continue
            if len(candidates) != 1:
                skipped_reasons[f"{spec.group}_no_unique_match"] += 1
                counts[skipped_key] += 1
                group_diag["noMatchRows"] += 1
                _diagnostic_reason(group_diag, "no_unique_match")
                _add_sample(group_diag["unmatchedScoringSamples"], _sample_from_row(row, reason="no_unique_match", key=row_entry["key"]))
                continue
            if _uses_unique_missing_side(row_entry, candidates[0]):
                _diagnostic_reason(group_diag, "team_or_opponent_unavailable_but_key_unique")
            joined = False
            for field in spec.join_fields:
                value = first_value(candidates[0]["row"], [field, _camel(field)], "")
                if _is_numeric(value):
                    row[field] = _format_number(to_float(value, math.nan), 6)
                    joined = True
                elif str(value or "").strip():
                    row[field] = str(value).strip()
                    joined = True
            if joined:
                counts[joined_key] += 1
            else:
                skipped_reasons[f"{spec.group}_matched_but_no_populated_fields"] += 1
                counts[skipped_key] += 1
                _diagnostic_reason(group_diag, "matched_but_no_populated_fields")
                _add_sample(group_diag["unmatchedScoringSamples"], _sample_from_row(row, reason="matched_but_no_populated_fields", key=row_entry["key"]))

        if counts[ambiguous_key]:
            warnings.append(f"{spec.group} skipped {counts[ambiguous_key]} ambiguous context rows.")
        counts["skippedByReason"] = dict(skipped_reasons)


def _public_artifacts(artifacts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    public: dict[str, dict[str, Any]] = {}
    for group, payload in artifacts.items():
        public[group] = {
            "path": payload.get("path"),
            "exists": bool(payload.get("exists")),
            "rows": int(payload.get("rows") or 0),
            "fields": list(payload.get("fields") or []),
            "warnings": list(payload.get("warnings") or []),
        }
    return public


def _new_diagnostics(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {group: {**_empty_group_diagnostics(), "rowsLoaded": int(payload.get("rows") or 0)} for group, payload in artifacts.items()}


def _board_alignment_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rowsWithCleanSubjectName": 0,
        "rowsWithSubjectTeam": 0,
        "rowsWithSubjectOpponent": 0,
        "rowsMissingSubjectTeam": 0,
        "rowsMissingSubjectOpponent": 0,
        "rowsSuspectedTeamOpponentReversed": 0,
        "rowsFixedTeamOpponentReversed": 0,
        "rowsSkippedUnsafeTeamInference": 0,
        "subjectRoleCounts": {},
        "sampleAlignmentFixes": [],
        "sampleMissingTeamRows": [],
        "sampleReversedCandidates": [],
    }
    roles: Counter[str] = Counter()
    for row in rows:
        role = str(first_value(row, ["subjectRole"], "") or "unknown").strip() or "unknown"
        roles[role] += 1
        subject_name = str(first_value(row, ["subjectName"], "") or "").strip()
        normalized_name = str(first_value(row, ["normalizedSubjectName"], "") or "").strip()
        subject_team = str(first_value(row, ["normalizedSubjectTeam", "subjectTeam"], "") or "").strip()
        subject_opponent = str(first_value(row, ["normalizedSubjectOpponent", "subjectOpponent"], "") or "").strip()
        warnings = set(str(first_value(row, ["subjectIdentityWarnings"], "") or "").split("|"))
        if subject_name and normalized_name:
            payload["rowsWithCleanSubjectName"] += 1
        if subject_team:
            payload["rowsWithSubjectTeam"] += 1
        else:
            payload["rowsMissingSubjectTeam"] += 1
            _add_sample(payload["sampleMissingTeamRows"], _sample_from_row(row, reason="missing_subject_team"))
        if subject_opponent:
            payload["rowsWithSubjectOpponent"] += 1
        else:
            payload["rowsMissingSubjectOpponent"] += 1
        if row.get("subjectTeamOpponentSuspectedReversed") is True:
            payload["rowsSuspectedTeamOpponentReversed"] += 1
            _add_sample(payload["sampleReversedCandidates"], _sample_from_row(row, reason="team_opponent_mismatch"))
        if row.get("subjectTeamOpponentFixed") is True:
            payload["rowsFixedTeamOpponentReversed"] += 1
            _add_sample(payload["sampleAlignmentFixes"], _sample_from_row(row, reason="team_opponent_reversed_fixed"))
        if "skipped_unsafe_team_inference" in warnings:
            payload["rowsSkippedUnsafeTeamInference"] += 1
    payload["subjectRoleCounts"] = dict(sorted(roles.items()))
    return payload


def _empty_group_diagnostics() -> dict[str, Any]:
    return {
        "rowsLoaded": 0,
        "rowsJoined": 0,
        "rowsSkipped": 0,
        "ambiguousRows": 0,
        "missingKeyRows": 0,
        "weakIdentityRows": 0,
        "noMatchRows": 0,
        "duplicateContextKeyRows": 0,
        "unmatchedContextSamples": [],
        "unmatchedScoringSamples": [],
        "contextJoinKeyExamples": [],
        "contextJoinSkipReasons": {},
    }


def _finalize_diagnostics(diagnostics: dict[str, Any], counts: dict[str, Any]) -> None:
    joined_keys = {
        "odds_movement": "oddsMovementRowsJoined",
        "player_recent_form": "playerRecentFormRowsJoined",
        "pitcher_context": "pitcherContextRowsJoined",
        "statcast": "statcastRowsJoined",
        "handedness_platoon": "handednessPlatoonRowsJoined",
    }
    skipped_keys = {
        "odds_movement": "oddsMovementRowsSkipped",
        "player_recent_form": "playerRecentFormRowsSkipped",
        "pitcher_context": "pitcherContextRowsSkipped",
        "statcast": "statcastRowsSkipped",
        "handedness_platoon": "handednessPlatoonRowsSkipped",
    }
    for group, payload in diagnostics.items():
        payload["rowsJoined"] = int(counts.get(joined_keys.get(group, ""), 0) or 0)
        payload["rowsSkipped"] = int(counts.get(skipped_keys.get(group, ""), 0) or 0)
        payload["contextJoinSkipReasons"] = dict(sorted(Counter(payload.get("contextJoinSkipReasons") or {}).items()))


def _odds_join_key(row: dict[str, Any], *, date_label: str, season: int, is_context: bool) -> tuple[str, str]:
    row_date = str(first_value(row, ["date", "game_date", "gameDate", "event_date"], "")).strip() or (date_label if is_context else "")
    row_season = str(first_value(row, ["season"], "")).strip() or str(season)
    player = normalize_player_name(first_value(row, ["player", "playerName", "name"], ""))
    market = model_market_key(first_value(row, ["market", "baseMarket"], ""))
    side = normalize_prop_side(
        first_value(row, ["side"], ""),
        first_value(row, ["rawLabel", "raw_label"], ""),
        first_value(row, ["label", "title", "name"], ""),
        first_value(row, ["outcome", "outcomeName", "outcome_name", "selection"], ""),
    )
    line = _line_key(first_value(row, ["line", "sportsbook_line", "prop_line"], ""))
    book = normalize_book_key(first_value(row, ["bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook"], ""))
    if row_date != date_label:
        return "", "date_mismatch"
    if row_season and str(row_season) != str(season):
        return "", "season_mismatch"
    missing = [
        name
        for name, value in (
            ("player", player),
            ("market", market),
            ("side", side),
            ("line", line),
            ("book", book),
        )
        if not value
    ]
    if missing:
        return "", "missing_" + "_".join(missing)
    return "|".join([date_label, str(season), player, market, _key(side), line, book]), ""


def _identity_context_entry(
    row: dict[str, Any],
    *,
    name_aliases: tuple[str, ...],
    team_aliases: tuple[str, ...],
    opponent_aliases: tuple[str, ...],
    date_label: str,
    season: int,
    is_context: bool,
    group: str,
) -> tuple[dict[str, Any] | None, str]:
    row_date = str(first_value(row, ["date", "game_date", "gameDate", "event_date"], "")).strip() or (date_label if is_context else "")
    row_season = str(first_value(row, ["season"], "")).strip() or str(season)
    name = normalize_player_name(first_value(row, list(name_aliases), ""))
    team = normalize_team(first_value(row, list(team_aliases), ""))
    opponent = normalize_opponent(first_value(row, list(opponent_aliases), "")) if opponent_aliases else ""
    if row_date != date_label:
        return None, "date_mismatch"
    if row_season and str(row_season) != str(season):
        return None, "season_mismatch"
    if not name:
        return None, "missing_name"
    if is_context and group in {"statcast", "handedness_platoon"}:
        if _flag_false(first_value(row, ["pregameSafe", "pregame_safe"], True)):
            return None, "not_pregame_safe"
        if _flag_false(first_value(row, ["labelsExcluded", "labels_excluded"], True)):
            return None, "labels_not_excluded"
        confidence = str(first_value(row, ["identityConfidence", "identity_confidence"], "") or "").strip().lower()
        if confidence in {"weak", "unknown"}:
            return None, "weak_or_unknown_identity"
    key = "|".join([date_label, str(season), name, team or "*", opponent or "*"])
    return {"key": key, "date": date_label, "season": str(season), "name": name, "team": team, "opponent": opponent, "row": row}, ""


def _entries_match(scoring: dict[str, Any], context: dict[str, Any]) -> bool:
    if scoring["date"] != context["date"] or scoring["season"] != context["season"]:
        return False
    if scoring["name"] != context["name"]:
        return False
    if scoring["team"] and context["team"] and scoring["team"] != context["team"]:
        return False
    if scoring["opponent"] and context["opponent"] and scoring["opponent"] != context["opponent"]:
        return False
    return True


def _uses_unique_missing_side(scoring: dict[str, Any], context: dict[str, Any]) -> bool:
    return bool((not scoring["team"] or not context["team"] or not scoring["opponent"] or not context["opponent"]))


def _entries_have_required_sides(scoring: dict[str, Any], context: dict[str, Any]) -> bool:
    return bool(scoring["team"] and context["team"])


def _flag_false(value: Any) -> bool:
    text = str(value).strip().lower()
    return text in {"0", "false", "no", "n"}


def _diagnostic_reason(payload: dict[str, Any], reason: str) -> None:
    reasons = Counter(payload.get("contextJoinSkipReasons") or {})
    reasons[reason or "unknown"] += 1
    payload["contextJoinSkipReasons"] = dict(reasons)


def _add_sample(samples: list[Any], sample: Any, *, limit: int = 10) -> None:
    if sample in samples:
        return
    if len(samples) < limit:
        samples.append(sample)


def _sample_from_row(row: dict[str, Any], *, reason: str, key: str = "") -> dict[str, Any]:
    return {
        "reason": reason,
        "key": key,
        "player": str(first_value(row, ["player", "playerName", "name", "batter_name", "player_name"], "") or "").strip(),
        "team": str(first_value(row, ["team", "teamAbbr", "team_abbr", "teamCode", "bat_team"], "") or "").strip(),
        "opponent": str(first_value(row, ["opponent", "opponentAbbr", "opponent_abbr", "opponentCode"], "") or "").strip(),
    }


def _identity_confidence(row: dict[str, Any], *, input_source: str) -> str:
    return str(identity_confidence_for_row(row, input_source=input_source).get("identityConfidence") or "unknown")


def _line_key(value: Any) -> str:
    parsed = to_float(value, math.nan)
    if math.isnan(parsed):
        return ""
    rounded = round(float(parsed), 4)
    return str(int(rounded)) if rounded.is_integer() else str(rounded).rstrip("0").rstrip(".")


def _is_numeric(value: Any) -> bool:
    parsed = to_float(value, math.nan)
    return not math.isnan(parsed)


def _format_number(value: float, places: int) -> float:
    rounded = round(float(value), places)
    return int(rounded) if rounded.is_integer() else rounded


def _key(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().split())


def _camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _spec_for_group(group: str) -> ContextArtifactSpec:
    for spec in CONTEXT_ARTIFACTS:
        if spec.group == group:
            return spec
    raise KeyError(group)
