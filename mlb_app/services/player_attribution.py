from __future__ import annotations

import re
from collections import Counter
from typing import Any

from mlb_app.services.team_match_utils import normalize_team_alias

ATTRIBUTION_CONTEXT_WARNING = "Context limited by unverified player/team attribution."

_PROP_SUFFIX_PATTERNS = (
    re.compile(r"\s+(?:pitcher\s+)?strikeouts?\s+thrown\s*$", re.IGNORECASE),
    re.compile(r"\s+(?:batter\s+)?hits?\s*$", re.IGNORECASE),
    re.compile(r"\s+total\s+bases?\s*$", re.IGNORECASE),
    re.compile(r"\s+home\s+runs?\s*$", re.IGNORECASE),
    re.compile(r"\s+rbi(?:s)?\s*$", re.IGNORECASE),
)

_INVALID_PLAYER_LABEL_PATTERNS = (
    re.compile(r"^\s*\d+\s*\+\s*(?:strikeouts?|hits?|total\s+bases?|home\s+runs?|rbis?)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:over|under)\s+\d+(?:\.\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:ladder|milestone|alternate|alt)\b", re.IGNORECASE),
)

_KNOWN_PLAYER_TEAMS = {
    "jazz chisholm": "NYY",
    "jazz chisholm jr": "NYY",
    "jasson dominguez": "NYY",
    "vladimir guerrero jr": "TOR",
    "vladimir guerrero": "TOR",
}


def clean_player_label(value: Any, *, market: Any = "", raw_label: Any = "") -> dict[str, Any]:
    raw = _clean(value)
    cleaned = " ".join(raw.replace("\u00a0", " ").split())
    cleaned = re.sub(r"\s+([,.])", r"\1", cleaned)
    warnings: list[str] = []
    invalid = _looks_invalid_player_label(cleaned)

    if cleaned:
        for pattern in _PROP_SUFFIX_PATTERNS:
            next_value = pattern.sub("", cleaned).strip()
            if next_value != cleaned and _looks_like_person_name(next_value):
                warnings.append(f"removed_market_suffix:{cleaned[len(next_value):].strip()}")
                cleaned = next_value
                break

    if not _looks_like_person_name(cleaned):
        invalid = True

    return {
        "rawPlayerName": raw,
        "cleanedPlayerName": cleaned if not invalid else "",
        "invalidPlayerLabel": invalid,
        "playerLabelWarnings": warnings,
    }


def resolve_attribution(row: dict[str, Any]) -> dict[str, Any]:
    raw_player = _clean(_first(row, "rawPlayerName", "sourcePlayerLabel", "sourcePlayerName", "player", "playerName", "name"))
    market = _clean(row.get("market"))
    label_result = clean_player_label(raw_player, market=market, raw_label=_first(row, "rawLabel", "side"))
    if not _is_player_market(market):
        label_result["invalidPlayerLabel"] = False
        label_result["cleanedPlayerName"] = raw_player
    cleaned_player = label_result["cleanedPlayerName"]
    raw_team = _clean(_first(row, "sourceTeam", "team", "team_abbr", "teamCode"))
    raw_opponent = _clean(_first(row, "sourceOpponent", "opponent", "opponent_abbr", "opponentCode"))
    resolved_team = normalize_team_alias(raw_team)
    resolved_opponent = normalize_team_alias(raw_opponent)

    warnings = list(label_result["playerLabelWarnings"])
    sources: list[str] = []
    if raw_player:
        sources.append("source_player")
    if raw_team:
        sources.append("source_team")
    if raw_opponent:
        sources.append("source_opponent")

    player_verified = bool(cleaned_player and not label_result["invalidPlayerLabel"])
    team_verified = _truthy(row.get("teamVerified")) or _truthy(row.get("playerTeamVerified"))
    opponent_verified = _truthy(row.get("opponentVerified"))
    status = "unverified"
    confidence = "unknown"
    conflict_reason = ""

    known_team = _KNOWN_PLAYER_TEAMS.get(_name_key(cleaned_player))
    if label_result["invalidPlayerLabel"]:
        status = "invalid_player_label"
        confidence = "unknown"
        player_verified = False
        warnings.append("invalid_player_label")
    elif known_team and resolved_team and known_team != resolved_team:
        status = "conflict"
        confidence = "low"
        team_verified = False
        opponent_verified = False
        conflict_reason = f"local_player_team_conflict:{cleaned_player}:{resolved_team}!={known_team}"
        warnings.append("possible_team_mismatch")
        sources.append("local_player_team_mapping")
    elif not raw_team or not raw_opponent:
        status = "source_missing"
        confidence = "low" if not (raw_team or raw_opponent) else "medium"
        warnings.append("missing_source_team_or_opponent")
    elif team_verified and opponent_verified:
        status = "verified"
        confidence = "verified"
    else:
        status = "inferred"
        confidence = "medium"
        warnings.append("team_opponent_inferred")

    context_allowed = confidence in {"verified", "high", "medium"} and status not in {"conflict", "invalid_player_label"}
    context_warning = confidence == "medium" and context_allowed
    if not context_allowed:
        warnings.append("context_limited_by_attribution")

    return {
        "attributionConfidence": confidence,
        "attributionStatus": status,
        "attributionWarnings": _unique(warnings),
        "attributionSources": _unique(sources),
        "teamVerified": bool(team_verified and status == "verified"),
        "opponentVerified": bool(opponent_verified and status == "verified"),
        "playerVerified": bool(player_verified and status not in {"invalid_player_label", "conflict"}),
        "cleanedPlayerName": cleaned_player,
        "rawPlayerName": raw_player,
        "sourceTeam": raw_team,
        "sourceOpponent": raw_opponent,
        "resolvedTeam": resolved_team,
        "resolvedOpponent": resolved_opponent,
        "resolvedGameId": _clean(_first(row, "resolvedGameId", "gameId", "gamePk", "eventId")),
        "attributionConflictReason": conflict_reason,
        "contextBlockedByAttribution": not context_allowed,
        "contextAllowedWithWarning": bool(context_warning),
    }


def apply_attribution(row: dict[str, Any]) -> dict[str, Any]:
    attribution = resolve_attribution(row)
    enriched = dict(row)
    enriched.update(attribution)
    if attribution["cleanedPlayerName"]:
        enriched["player"] = attribution["cleanedPlayerName"]
        enriched["playerDisplayName"] = attribution["cleanedPlayerName"]
        enriched["cleanedPlayer"] = attribution["cleanedPlayerName"]

    warnings = _unique([*(enriched.get("trustWarnings") or []), *attribution["attributionWarnings"]])
    if warnings:
        enriched["trustWarnings"] = warnings
        enriched["warningCount"] = len(warnings)

    trust = dict(enriched.get("trust") or {})
    prop_identity = dict(trust.get("propIdentity") or {})
    prop_identity.update(
        {
            "player": enriched.get("player", ""),
            "team": enriched.get("team", ""),
            "opponent": enriched.get("opponent", ""),
            "identityConfidence": attribution_confidence_to_identity(attribution["attributionConfidence"], attribution["attributionStatus"]),
            "identityWarnings": attribution["attributionWarnings"],
            "playerTeamVerified": attribution["teamVerified"],
            "opponentVerified": attribution["opponentVerified"],
            "attributionStatus": attribution["attributionStatus"],
        }
    )
    trust["propIdentity"] = prop_identity
    trust["attribution"] = {
        key: attribution[key]
        for key in (
            "attributionConfidence",
            "attributionStatus",
            "attributionWarnings",
            "teamVerified",
            "opponentVerified",
            "playerVerified",
            "contextBlockedByAttribution",
            "contextAllowedWithWarning",
        )
    }
    enriched["trust"] = trust
    return enriched


def attribution_allows_context(row: dict[str, Any]) -> bool:
    if "contextBlockedByAttribution" not in row:
        row = apply_attribution(row)
    return not bool(row.get("contextBlockedByAttribution"))


def attribution_confidence_to_identity(confidence: Any, status: Any = "") -> str:
    confidence_text = _clean(confidence)
    status_text = _clean(status)
    if confidence_text in {"verified", "high"} and status_text == "verified":
        return "strong"
    if confidence_text == "medium":
        return "medium"
    if confidence_text == "low":
        return "weak"
    return "unknown"


def attribution_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = [apply_attribution(row) if "attributionConfidence" not in row else row for row in rows]
    counts = Counter(_clean(row.get("attributionConfidence")) or "unknown" for row in enriched)
    status_counts = Counter(_clean(row.get("attributionStatus")) or "unknown" for row in enriched)
    return {
        "attributionRowsVerified": counts.get("verified", 0),
        "attributionRowsHigh": counts.get("high", 0),
        "attributionRowsMedium": counts.get("medium", 0),
        "attributionRowsLow": counts.get("low", 0),
        "attributionRowsUnknown": counts.get("unknown", 0),
        "attributionRowsConflict": status_counts.get("conflict", 0),
        "attributionRowsInvalidPlayerLabel": status_counts.get("invalid_player_label", 0),
        "rowsBlockedFromContextByAttribution": sum(1 for row in enriched if row.get("contextBlockedByAttribution")),
        "rowsAllowedContextWithWarning": sum(1 for row in enriched if row.get("contextAllowedWithWarning")),
        "sampleAttributionConflicts": _samples(enriched, lambda row: row.get("attributionStatus") == "conflict"),
        "sampleWeakAttributionRows": _samples(enriched, lambda row: row.get("attributionConfidence") in {"low", "unknown"}),
        "sampleInvalidPlayerLabels": _samples(enriched, lambda row: row.get("attributionStatus") == "invalid_player_label"),
        "sampleCleanedPlayerNames": _samples(enriched, lambda row: bool(row.get("rawPlayerName") and row.get("cleanedPlayerName") and row.get("rawPlayerName") != row.get("cleanedPlayerName"))),
        "sampleTeamCorrections": _samples(enriched, lambda row: bool(row.get("attributionConflictReason"))),
        "sampleRowsBlockedFromModelContext": _samples(enriched, lambda row: row.get("contextBlockedByAttribution")),
    }


def _samples(rows: list[dict[str, Any]], predicate: Any) -> list[dict[str, Any]]:
    sample = []
    for row in rows:
        if not predicate(row):
            continue
        sample.append(
            {
                "player": _clean(row.get("player")),
                "rawPlayerName": _clean(row.get("rawPlayerName")),
                "team": _clean(row.get("team")),
                "opponent": _clean(row.get("opponent")),
                "market": _clean(row.get("market")),
                "attributionConfidence": _clean(row.get("attributionConfidence")),
                "attributionStatus": _clean(row.get("attributionStatus")),
                "warnings": list(row.get("attributionWarnings") or [])[:3],
            }
        )
        if len(sample) >= 5:
            break
    return sample


def _looks_invalid_player_label(value: str) -> bool:
    if not value:
        return True
    return any(pattern.search(value) for pattern in _INVALID_PLAYER_LABEL_PATTERNS)


def _is_player_market(value: Any) -> bool:
    market = _clean(value).lower()
    return market.startswith("batter_") or market.startswith("pitcher_")


def _looks_like_person_name(value: str) -> bool:
    if _looks_invalid_player_label(value):
        return False
    tokens = [token for token in re.split(r"\s+", value.strip()) if token]
    if len(tokens) < 2 or len(tokens) > 5:
        return False
    return all(re.search(r"[A-Za-z]", token) for token in tokens)


def _name_key(value: Any) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", lambda match: match.group(1), text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return _clean(value).lower() in {"1", "true", "yes", "y", "verified"}


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
