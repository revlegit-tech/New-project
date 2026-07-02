from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

PLAYERBOARD_SCHEMA_VERSION = "playerboard.v3"

PLAYERBOARD_FIELDS: list[str] = [
    "snapshotAt",
    "season",
    "date",
    "market",
    "marketDisplay",
    "baseMarket",
    "isAltMarket",
    "player",
    "team",
    "opponent",
    "pitcher",
    "line",
    "americanOdds",
    "book",
    "bookKey",
    "bookCount",
    "books",
    "finalProbabilityPercent",
    "sportsbookImpliedPercent",
    "finalEdgePercent",
    "confidence",
    "recommendation",
    "weatherAdjustmentPercent",
    "savantAdjustmentPercent",
    "oddsMovementAdjustmentPercent",
    "missingData",
    "originalMarket",
    "rawLabel",
    "marketFamily",
    "hitRates",
    "recentGames",
    "attributionConfidence",
    "attributionStatus",
    "attributionCorrectionApplied",
    "attributionCorrectionReason",
    "attributionWarnings",
    "attributionSources",
    "teamVerified",
    "opponentVerified",
    "playerVerified",
    "cleanedPlayerName",
    "rawPlayerName",
    "sourceTeam",
    "sourceOpponent",
    "resolvedTeam",
    "resolvedOpponent",
    "resolvedTeamAbbr",
    "resolvedOpponentAbbr",
    "resolvedGameId",
    "attributionConflictReason",
    "originalTeam",
    "originalOpponent",
    "correctedTeam",
    "correctedOpponent",
    "playerTeamEvidenceStatus",
    "rosterEvidenceAvailable",
    "rosterMatchStatus",
    "playerTeamEvidenceSources",
    "playerTeamEvidenceWarnings",
    "contextBlockedByAttribution",
    "contextAllowedWithWarning",
]

# Required fields are intentionally limited to values the app needs to identify,
# filter, and price a row. The remaining fields can be backfilled for known
# legacy CSVs without losing the betting row itself.
REQUIRED_PLAYERBOARD_FIELDS: tuple[str, ...] = (
    "snapshotAt",
    "season",
    "date",
    "market",
    "player",
    "team",
    "opponent",
    "line",
    "americanOdds",
)

OPTIONAL_PLAYERBOARD_FIELDS: tuple[str, ...] = tuple(
    field for field in PLAYERBOARD_FIELDS if field not in REQUIRED_PLAYERBOARD_FIELDS
)

COMPUTED_PLAYERBOARD_FIELDS: tuple[str, ...] = (
    "marketDisplay",
    "baseMarket",
    "isAltMarket",
    "finalProbabilityPercent",
    "sportsbookImpliedPercent",
    "finalEdgePercent",
    "confidence",
    "recommendation",
    "marketFamily",
)

DEPRECATED_PLAYERBOARD_FIELDS: tuple[str, ...] = ()

_JSON_LIST_FIELDS = {
    "books",
    "missingData",
    "hitRates",
    "recentGames",
    "attributionWarnings",
    "attributionSources",
    "playerTeamEvidenceSources",
    "playerTeamEvidenceWarnings",
}
_BOOL_FIELDS = {
    "isAltMarket",
    "attributionCorrectionApplied",
    "rosterEvidenceAvailable",
    "teamVerified",
    "opponentVerified",
    "playerVerified",
    "contextBlockedByAttribution",
    "contextAllowedWithWarning",
}
_INT_FIELDS = {"season", "americanOdds", "bookCount"}
_FLOAT_FIELDS = {
    "line",
    "finalProbabilityPercent",
    "sportsbookImpliedPercent",
    "finalEdgePercent",
    "weatherAdjustmentPercent",
    "savantAdjustmentPercent",
    "oddsMovementAdjustmentPercent",
}


@dataclass(frozen=True)
class SchemaValidationResult:
    """Structured result for a playerboard CSV header validation."""

    ok: bool
    version: str
    reason: str = ""
    missing_required_fields: tuple[str, ...] = ()
    missing_optional_fields: tuple[str, ...] = ()
    extra_fields: tuple[str, ...] = ()
    deprecated_fields: tuple[str, ...] = ()
    order_matches: bool = True
    warnings: tuple[str, ...] = ()
    expected_fields: tuple[str, ...] = field(default_factory=lambda: tuple(PLAYERBOARD_FIELDS))
    observed_fields: tuple[str, ...] = ()

    @property
    def actionable_message(self) -> str:
        if self.ok:
            if self.warnings:
                return "; ".join(self.warnings)
            return ""
        parts = [self.reason or "schema_invalid"]
        if self.missing_required_fields:
            parts.append("missing required fields: " + ", ".join(self.missing_required_fields))
        if self.extra_fields:
            parts.append("extra fields: " + ", ".join(self.extra_fields))
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schemaVersion": self.version,
            "reason": self.reason,
            "message": self.actionable_message,
            "missingRequiredFields": list(self.missing_required_fields),
            "missingOptionalFields": list(self.missing_optional_fields),
            "extraFields": list(self.extra_fields),
            "deprecatedFields": list(self.deprecated_fields),
            "orderMatches": self.order_matches,
            "warnings": list(self.warnings),
            "expectedFields": list(self.expected_fields),
            "observedFields": list(self.observed_fields),
        }


class PlayerboardSchemaError(ValueError):
    """Raised when a playerboard schema cannot be safely interpreted."""

    def __init__(self, result: SchemaValidationResult) -> None:
        super().__init__(result.actionable_message or result.reason or "playerboard schema validation failed")
        self.result = result


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _as_tuple(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in values if str(value).strip())


def validate_playerboard_header(header: list[str]) -> SchemaValidationResult:
    """Validate a playerboard CSV header against the versioned contract.

    This validator is deliberately field-name based. Column order drift is
    reported as a warning, not a failure, because CSV DictReader can safely read
    rows by field name when all required fields are present.
    """

    observed = _as_tuple(header)
    observed_set = set(observed)
    expected = tuple(PLAYERBOARD_FIELDS)
    expected_set = set(expected)
    required_set = set(REQUIRED_PLAYERBOARD_FIELDS)

    missing_required = tuple(field for field in REQUIRED_PLAYERBOARD_FIELDS if field not in observed_set)
    missing_optional = tuple(field for field in OPTIONAL_PLAYERBOARD_FIELDS if field not in observed_set)
    extra = tuple(field for field in observed if field not in expected_set)
    deprecated = tuple(field for field in observed if field in DEPRECATED_PLAYERBOARD_FIELDS)
    order_matches = observed == expected

    if missing_required:
        return SchemaValidationResult(
            ok=False,
            version="unknown",
            reason="missing_required_fields",
            missing_required_fields=missing_required,
            missing_optional_fields=missing_optional,
            extra_fields=extra,
            deprecated_fields=deprecated,
            order_matches=order_matches,
            observed_fields=observed,
        )

    warnings: list[str] = []
    version = PLAYERBOARD_SCHEMA_VERSION
    if missing_optional:
        version = "playerboard.legacy.v2"
        warnings.append("known legacy playerboard schema can be upgraded by filling optional/computed fields")
    if extra:
        warnings.append("extra fields will be preserved in normalized rows but ignored by strict CSV exports")
    if not order_matches and set(observed) == expected_set:
        warnings.append("column order differs from the canonical contract but field names are stable")
    if deprecated:
        warnings.append("deprecated fields are present: " + ", ".join(deprecated))

    return SchemaValidationResult(
        ok=True,
        version=version,
        reason="" if not warnings else "schema_warning",
        missing_optional_fields=missing_optional,
        extra_fields=extra,
        deprecated_fields=deprecated,
        order_matches=order_matches,
        warnings=tuple(warnings),
        observed_fields=observed,
    )


def require_valid_playerboard_header(header: list[str]) -> SchemaValidationResult:
    result = validate_playerboard_header(header)
    if not result.ok:
        raise PlayerboardSchemaError(result)
    return result


def normalize_market_value(value: Any) -> str:
    text = _clean(value).lower()
    text = text.replace(" ", "_").replace("-", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def base_market_value(market: Any) -> str:
    normalized = normalize_market_value(market)
    return normalized[:-4] if normalized.endswith("_alt") else normalized


def market_family_value(market: Any) -> str:
    base = base_market_value(market)
    if base.startswith("batter_"):
        return "batter"
    if base.startswith("pitcher_"):
        return "pitcher"
    if base.startswith("team_"):
        return "team"
    if (
        base.startswith("game_")
        or base.startswith("first_")
        or base.startswith("run_line")
        or base.startswith("moneyline")
    ):
        return "game"
    return "other"


def market_display_value(market: Any, raw_label: Any = "") -> str:
    normalized = normalize_market_value(market)
    label = _clean(raw_label)
    if normalized == "batter_hits_alt":
        return f"Batter Hits Ladder - {label}" if label else "Batter Hits Ladder"
    if normalized == "batter_total_bases_alt":
        return f"Batter Total Bases Ladder - {label}" if label else "Batter Total Bases Ladder"
    if normalized == "batter_home_runs_alt":
        return f"Batter Home Runs Alt - {label}" if label else "Batter Home Runs Alt"
    if normalized == "pitcher_strikeouts_alt":
        return f"Pitcher Strikeouts Ladder - {label}" if label else "Pitcher Strikeouts Ladder"
    if normalized == "pitcher_hits_allowed_alt":
        return f"Pitcher Hits Allowed Ladder - {label}" if label else "Pitcher Hits Allowed Ladder"
    if normalized == "pitcher_earned_runs_alt":
        return f"Pitcher Earned Runs Ladder - {label}" if label else "Pitcher Earned Runs Ladder"
    return normalized.replace("_", " ").title()


def _parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in {None, ""}:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return [value]
    return [value]


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def _parse_int(value: Any) -> int | None:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any) -> float | None:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def normalize_playerboard_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return an app-ready row with contract fields, safe defaults, and extras.

    Canonical CSV exports can still write only ``PLAYERBOARD_FIELDS``. The
    normalized in-memory representation keeps extra fields under ``_extra`` so a
    forward-compatible producer does not lose data during read paths.
    """

    normalized: dict[str, Any] = {}
    for field in PLAYERBOARD_FIELDS:
        value = row.get(field, "")
        if field in _JSON_LIST_FIELDS:
            normalized[field] = _parse_json_list(value)
        elif field in _BOOL_FIELDS:
            normalized[field] = _parse_bool(value)
        elif field in _INT_FIELDS:
            normalized[field] = _parse_int(value)
        elif field in _FLOAT_FIELDS:
            normalized[field] = _parse_float(value)
        else:
            normalized[field] = _clean(value)

    market = normalize_market_value(normalized.get("market"))
    normalized["market"] = market
    normalized["baseMarket"] = _clean(normalized.get("baseMarket")) or base_market_value(market)
    normalized["isAltMarket"] = bool(normalized.get("isAltMarket")) or market.endswith("_alt")
    normalized["marketDisplay"] = _clean(normalized.get("marketDisplay")) or market_display_value(
        market, normalized.get("rawLabel")
    )
    normalized["marketFamily"] = _clean(normalized.get("marketFamily")) or market_family_value(market)
    normalized["schemaVersion"] = PLAYERBOARD_SCHEMA_VERSION

    extras = {key: value for key, value in row.items() if key not in set(PLAYERBOARD_FIELDS)}
    if extras:
        normalized["_extra"] = extras

    return normalized
