from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
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
    ContextArtifactSpec("statcast", "statcast", "statcast_context_{date}.csv"),
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
        output = [dict(row) for row in rows]
        artifacts = self.load_artifacts(date_label=date_label)
        warnings: list[str] = []
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
            "loadedByGroup": {group: int(payload.get("rows") or 0) for group, payload in artifacts.items()},
            "joinedByGroup": {"odds_movement": 0, "player_recent_form": 0, "pitcher_context": 0},
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
                context_name_aliases=("player", "playerName", "name"),
                row_name_aliases=("player", "playerName", "name"),
                context_team_aliases=("team", "teamAbbr", "team_abbr", "teamCode"),
                row_team_aliases=("team", "teamAbbr", "team_abbr", "teamCode"),
                loaded_key="playerRecentFormRowsLoaded",
                joined_key="playerRecentFormRowsJoined",
                skipped_key="playerRecentFormRowsSkipped",
                ambiguous_key="playerRecentFormAmbiguousRows",
                counts=counts,
                warnings=warnings,
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
                context_name_aliases=("pitcher", "player", "playerName", "name"),
                row_name_aliases=("pitcher", "probablePitcher", "opposingPitcher"),
                context_team_aliases=("team", "teamAbbr", "team_abbr", "teamCode"),
                row_team_aliases=("opponent", "opponentAbbr", "opponent_abbr", "opponentCode", "team", "teamAbbr"),
                loaded_key="pitcherContextRowsLoaded",
                joined_key="pitcherContextRowsJoined",
                skipped_key="pitcherContextRowsSkipped",
                ambiguous_key="pitcherContextAmbiguousRows",
                counts=counts,
                warnings=warnings,
            )
        elif artifacts["pitcher_context"].get("exists"):
            counts["pitcherContextRowsSkipped"] = len(output)

        counts["skippedByReason"] = dict(sorted(Counter(counts["skippedByReason"]).items()))
        counts["joinedByGroup"]["odds_movement"] = counts["oddsMovementRowsJoined"]
        counts["joinedByGroup"]["player_recent_form"] = counts["playerRecentFormRowsJoined"]
        counts["joinedByGroup"]["pitcher_context"] = counts["pitcherContextRowsJoined"]
        if int(artifacts["odds_movement"]["rows"] or 0) > 0 and counts["oddsMovementRowsJoined"] == 0:
            warnings.append("odds_movement context artifact available but no scoring rows joined safely.")
        if int(artifacts["player_recent_form"]["rows"] or 0) > 0 and counts["playerRecentFormRowsJoined"] == 0:
            warnings.append("player_recent_form context artifact available but no scoring rows joined safely.")
        if int(artifacts["pitcher_context"]["rows"] or 0) > 0 and counts["pitcherContextRowsJoined"] == 0:
            warnings.append("pitcher_context context artifact available but no scoring rows joined safely.")
        return ContextJoinResult(rows=output, artifacts=_public_artifacts(artifacts), counts=counts, warnings=sorted(set(warnings)))

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
        loaded_key: str,
        joined_key: str,
        skipped_key: str,
        ambiguous_key: str,
        counts: dict[str, Any],
        warnings: list[str],
    ) -> None:
        context_by_key: dict[str, list[dict[str, Any]]] = {}
        ambiguous_keys: set[str] = set()
        skipped_reasons: Counter[str] = Counter(counts.get("skippedByReason") or {})

        for context_row in context_rows:
            key, reason = _identity_context_key(
                context_row,
                name_aliases=context_name_aliases,
                team_aliases=context_team_aliases,
                date_label=date_label,
                season=season,
                is_context=True,
            )
            if not key:
                skipped_reasons[f"{spec.group}_context_{reason}"] += 1
                continue
            context_by_key.setdefault(key, []).append(context_row)
        for key, candidates in context_by_key.items():
            if len(candidates) > 1:
                ambiguous_keys.add(key)
                counts[ambiguous_key] += len(candidates)

        for row in rows:
            if _identity_confidence(row, input_source=input_source) not in {"strong", "medium"}:
                skipped_reasons[f"{spec.group}_weak_or_unknown_identity"] += 1
                counts[skipped_key] += 1
                continue
            key, reason = _identity_context_key(
                row,
                name_aliases=row_name_aliases,
                team_aliases=row_team_aliases,
                date_label=date_label,
                season=season,
                is_context=False,
            )
            if not key:
                skipped_reasons[f"{spec.group}_{reason}"] += 1
                counts[skipped_key] += 1
                continue
            if key in ambiguous_keys:
                skipped_reasons[f"{spec.group}_ambiguous_match"] += 1
                counts[skipped_key] += 1
                continue
            matches = context_by_key.get(key) or []
            if len(matches) != 1:
                skipped_reasons[f"{spec.group}_no_unique_match"] += 1
                counts[skipped_key] += 1
                continue
            joined = False
            for field in spec.join_fields:
                value = first_value(matches[0], [field, _camel(field)], "")
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


def _odds_join_key(row: dict[str, Any], *, date_label: str, season: int, is_context: bool) -> tuple[str, str]:
    row_date = str(first_value(row, ["date", "game_date", "gameDate", "event_date"], "")).strip() or (date_label if is_context else "")
    row_season = str(first_value(row, ["season"], "")).strip() or str(season)
    player = _key(first_value(row, ["player", "playerName", "name"], ""))
    market = model_market_key(first_value(row, ["market", "baseMarket"], ""))
    side = normalize_prop_side(
        first_value(row, ["side"], ""),
        first_value(row, ["rawLabel", "raw_label"], ""),
        first_value(row, ["label", "title", "name"], ""),
        first_value(row, ["outcome", "outcomeName", "outcome_name", "selection"], ""),
    )
    line = _line_key(first_value(row, ["line", "sportsbook_line", "prop_line"], ""))
    book = _key(first_value(row, ["bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook"], ""))
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


def _identity_context_key(
    row: dict[str, Any],
    *,
    name_aliases: tuple[str, ...],
    team_aliases: tuple[str, ...],
    date_label: str,
    season: int,
    is_context: bool,
) -> tuple[str, str]:
    row_date = str(first_value(row, ["date", "game_date", "gameDate", "event_date"], "")).strip() or (date_label if is_context else "")
    row_season = str(first_value(row, ["season"], "")).strip() or str(season)
    name = _key(first_value(row, list(name_aliases), ""))
    team = _key(first_value(row, list(team_aliases), ""))
    if row_date != date_label:
        return "", "date_mismatch"
    if row_season and str(row_season) != str(season):
        return "", "season_mismatch"
    if not name:
        return "", "missing_name"
    if not team:
        return "", "missing_team"
    return "|".join([date_label, str(season), name, team]), ""


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
