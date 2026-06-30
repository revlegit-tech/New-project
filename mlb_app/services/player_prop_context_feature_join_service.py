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
    ContextArtifactSpec("player_recent_form", "player_recent_form", "player_recent_form_{date}.csv"),
    ContextArtifactSpec("pitcher_context", "pitcher_context", "pitcher_context_{date}.csv"),
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
            "loadedByGroup": {group: int(payload.get("rows") or 0) for group, payload in artifacts.items()},
            "joinedByGroup": {"odds_movement": 0},
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

        counts["skippedByReason"] = dict(sorted(Counter(counts["skippedByReason"]).items()))
        counts["joinedByGroup"]["odds_movement"] = counts["oddsMovementRowsJoined"]
        if int(artifacts["odds_movement"]["rows"] or 0) > 0 and counts["oddsMovementRowsJoined"] == 0:
            warnings.append("odds_movement context artifact available but no rows joined.")
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
