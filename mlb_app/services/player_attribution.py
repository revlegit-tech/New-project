from __future__ import annotations

import re
from collections import Counter
from typing import Any

from mlb_app.services.player_team_resolver import SlateRosterIndex, resolve_player_team
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


def resolve_attribution(row: dict[str, Any], roster_index: SlateRosterIndex | None = None) -> dict[str, Any]:
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
    original_team = _clean(_first(row, "originalTeam", "team", "sourceTeam", "team_abbr", "teamCode"))
    original_opponent = _clean(_first(row, "originalOpponent", "opponent", "sourceOpponent", "opponent_abbr", "opponentCode"))
    team_resolution = resolve_player_team(
        player_name=cleaned_player,
        source_team=raw_team,
        source_opponent=raw_opponent,
        home_team=_first(row, "homeTeam", "home_team", "home"),
        away_team=_first(row, "awayTeam", "away_team", "away"),
        player_id=_first(row, "playerId", "mlbPlayerId", "player_id"),
        roster_index=roster_index,
    )

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
    corrected_team = ""
    corrected_opponent = ""
    correction_applied = False
    correction_reason = ""
    evidence_status = team_resolution.status
    evidence_sources = list(team_resolution.sources)
    evidence_warnings = list(team_resolution.warnings)
    resolved_team_abbr = resolved_team
    resolved_opponent_abbr = resolved_opponent

    if label_result["invalidPlayerLabel"]:
        status = "invalid_player_label"
        confidence = "unknown"
        player_verified = False
        warnings.append("invalid_player_label")
        evidence_status = "missing"
    elif team_resolution.status == "ambiguous":
        status = "ambiguous"
        confidence = "low"
        team_verified = False
        opponent_verified = False
        warnings.extend(["ambiguous_player_name", "context_limited_by_attribution"])
    elif team_resolution.status == "conflict":
        status = "conflict"
        confidence = "low"
        team_verified = False
        opponent_verified = False
        conflict_reason = team_resolution.reason or f"local_player_team_conflict:{cleaned_player}:{resolved_team}!={team_resolution.team_abbr}"
        warnings.append("possible_team_mismatch")
        sources.extend(evidence_sources)
    elif team_resolution.verified:
        corrected_team = team_resolution.team
        corrected_opponent = team_resolution.opponent
        resolved_team = corrected_team
        resolved_opponent = corrected_opponent
        resolved_team_abbr = team_resolution.team_abbr
        resolved_opponent_abbr = team_resolution.opponent_abbr
        team_verified = True
        opponent_verified = bool(team_resolution.opponent_abbr)
        status = "verified" if team_resolution.status == "verified" else "corrected"
        confidence = "verified" if status == "verified" else "high"
        sources.extend(evidence_sources)
        if team_resolution.status != "verified":
            correction_applied = bool(raw_team and resolved_team_abbr and raw_team and normalize_team_alias(raw_team) != resolved_team_abbr)
            correction_reason = team_resolution.reason or "team_verified_by_roster"
            warnings.append("corrected_team_from_roster")
            if correction_applied:
                warnings.append("source_team_mismatch_corrected")
    elif not raw_team or not raw_opponent:
        status = "source_missing"
        confidence = "low"
        warnings.append("missing_source_team_or_opponent")
    elif team_verified and opponent_verified:
        status = "verified"
        confidence = "verified"
    else:
        status = "inferred_low_confidence" if _is_player_market(market) else "inferred"
        confidence = "low" if _is_player_market(market) else "medium"
        warnings.append("team_opponent_inferred")

    context_allowed = confidence in {"verified", "high", "medium"} and status not in {"conflict", "ambiguous", "invalid_player_label", "inferred_low_confidence"}
    context_warning = confidence == "medium" and context_allowed
    if not context_allowed:
        warnings.append("context_limited_by_attribution")

    return {
        "attributionConfidence": confidence,
        "attributionStatus": status,
        "attributionWarnings": _unique(warnings),
        "attributionSources": _unique(sources),
        "teamVerified": bool(team_verified and status in {"verified", "corrected"}),
        "opponentVerified": bool(opponent_verified and status in {"verified", "corrected"}),
        "playerVerified": bool(player_verified and status not in {"invalid_player_label", "conflict"}),
        "cleanedPlayerName": cleaned_player,
        "rawPlayerName": raw_player,
        "sourceTeam": raw_team,
        "sourceOpponent": raw_opponent,
        "resolvedTeam": resolved_team,
        "resolvedOpponent": resolved_opponent,
        "resolvedTeamAbbr": resolved_team_abbr,
        "resolvedOpponentAbbr": resolved_opponent_abbr,
        "resolvedGameId": _clean(_first(row, "resolvedGameId", "gameId", "gamePk", "eventId")),
        "attributionConflictReason": conflict_reason,
        "attributionCorrectionApplied": correction_applied,
        "attributionCorrectionReason": correction_reason,
        "originalTeam": original_team,
        "originalOpponent": original_opponent,
        "correctedTeam": corrected_team if correction_applied else "",
        "correctedOpponent": corrected_opponent if correction_applied else "",
        "playerTeamEvidenceStatus": evidence_status,
        "playerTeamEvidenceSources": _unique(evidence_sources),
        "playerTeamEvidenceWarnings": _unique(evidence_warnings),
        "contextBlockedByAttribution": not context_allowed,
        "contextAllowedWithWarning": bool(context_warning),
    }


def apply_attribution(row: dict[str, Any], roster_index: SlateRosterIndex | None = None) -> dict[str, Any]:
    attribution = resolve_attribution(row, roster_index=roster_index)
    enriched = dict(row)
    enriched.update(attribution)
    if attribution["cleanedPlayerName"]:
        enriched["player"] = attribution["cleanedPlayerName"]
        enriched["playerDisplayName"] = attribution["cleanedPlayerName"]
        enriched["cleanedPlayer"] = attribution["cleanedPlayerName"]
    if attribution["attributionCorrectionApplied"]:
        enriched["team"] = attribution["correctedTeam"]
        enriched["opponent"] = attribution["correctedOpponent"]
    elif attribution["teamVerified"] and attribution["resolvedTeam"]:
        enriched["team"] = attribution["resolvedTeam"]
        enriched["opponent"] = attribution["resolvedOpponent"]

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
            "attributionCorrectionApplied": attribution["attributionCorrectionApplied"],
            "attributionCorrectionReason": attribution["attributionCorrectionReason"],
            "playerTeamEvidenceStatus": attribution["playerTeamEvidenceStatus"],
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
            "attributionCorrectionApplied",
            "attributionCorrectionReason",
            "playerTeamEvidenceStatus",
            "playerTeamEvidenceSources",
            "playerTeamEvidenceWarnings",
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
    if confidence_text in {"verified", "high"} and status_text in {"verified", "corrected"}:
        return "strong"
    if confidence_text == "medium":
        return "medium"
    if confidence_text == "low":
        return "weak"
    return "unknown"


def attribution_diagnostics(rows: list[dict[str, Any]], roster_index: SlateRosterIndex | None = None) -> dict[str, Any]:
    enriched = [apply_attribution(row, roster_index=roster_index) if "attributionConfidence" not in row else row for row in rows]
    counts = Counter(_clean(row.get("attributionConfidence")) or "unknown" for row in enriched)
    status_counts = Counter(_clean(row.get("attributionStatus")) or "unknown" for row in enriched)
    return {
        "attributionRowsVerified": counts.get("verified", 0),
        "attributionRowsHigh": counts.get("high", 0),
        "attributionRowsMedium": counts.get("medium", 0),
        "attributionRowsLow": counts.get("low", 0),
        "attributionRowsUnknown": counts.get("unknown", 0),
        "attributionRowsConflict": status_counts.get("conflict", 0),
        "attributionRowsCorrected": sum(1 for row in enriched if row.get("attributionCorrectionApplied")),
        "attributionRowsCorrectedFromRoster": sum(1 for row in enriched if row.get("attributionCorrectionApplied") and "local_roster_seed" in (row.get("playerTeamEvidenceSources") or [])),
        "attributionRowsCorrectedFromGameLogs": sum(1 for row in enriched if row.get("attributionCorrectionApplied") and "game_log" in (row.get("playerTeamEvidenceSources") or [])),
        "attributionRowsVerifiedAfterCorrection": sum(1 for row in enriched if row.get("attributionCorrectionApplied") and row.get("teamVerified") and row.get("opponentVerified")),
        "attributionRowsStillConflict": status_counts.get("conflict", 0),
        "attributionRowsAmbiguous": status_counts.get("ambiguous", 0),
        "attributionRowsNoRosterEvidence": sum(1 for row in enriched if "no_roster_evidence" in (row.get("playerTeamEvidenceWarnings") or [])),
        "contextRowsUnblockedByCorrection": sum(1 for row in enriched if row.get("attributionCorrectionApplied") and not row.get("contextBlockedByAttribution")),
        "predictionRowsUnblockedByCorrection": sum(1 for row in enriched if row.get("attributionCorrectionApplied") and not row.get("contextBlockedByAttribution")),
        "attributionRowsInvalidPlayerLabel": status_counts.get("invalid_player_label", 0),
        "rowsBlockedFromContextByAttribution": sum(1 for row in enriched if row.get("contextBlockedByAttribution")),
        "rowsAllowedContextWithWarning": sum(1 for row in enriched if row.get("contextAllowedWithWarning")),
        "sampleAttributionConflicts": _samples(enriched, lambda row: row.get("attributionStatus") == "conflict"),
        "sampleWeakAttributionRows": _samples(enriched, lambda row: row.get("attributionConfidence") in {"low", "unknown"}),
        "sampleInvalidPlayerLabels": _samples(enriched, lambda row: row.get("attributionStatus") == "invalid_player_label"),
        "sampleCleanedPlayerNames": _samples(enriched, lambda row: bool(row.get("rawPlayerName") and row.get("cleanedPlayerName") and row.get("rawPlayerName") != row.get("cleanedPlayerName"))),
        "sampleTeamCorrections": _samples(enriched, lambda row: bool(row.get("attributionConflictReason"))),
        "sampleCorrectedRows": _samples(enriched, lambda row: bool(row.get("attributionCorrectionApplied"))),
        "sampleAmbiguousRows": _samples(enriched, lambda row: row.get("attributionStatus") == "ambiguous"),
        "sampleUncorrectedConflicts": _samples(enriched, lambda row: row.get("attributionStatus") == "conflict"),
        "sampleRosterEvidenceMatches": _samples(enriched, lambda row: row.get("playerTeamEvidenceStatus") in {"verified", "roster_match"}),
        "sampleRosterEvidenceMisses": _samples(enriched, lambda row: "no_roster_evidence" in (row.get("playerTeamEvidenceWarnings") or [])),
        "sampleRowsBlockedFromModelContext": _samples(enriched, lambda row: row.get("contextBlockedByAttribution")),
        "rosterResolverRowsChecked": sum(1 for row in enriched if _is_player_market(row.get("market"))),
        "rosterResolverRowsMatchedOneSide": sum(1 for row in enriched if row.get("playerTeamEvidenceStatus") in {"verified", "roster_match"}),
        "rosterResolverRowsCorrected": sum(1 for row in enriched if row.get("attributionCorrectionApplied") and row.get("playerTeamEvidenceStatus") == "roster_match"),
        "rosterResolverRowsAlreadyVerified": sum(1 for row in enriched if row.get("attributionStatus") == "verified" and row.get("playerTeamEvidenceStatus") == "verified"),
        "rosterResolverRowsAmbiguous": status_counts.get("ambiguous", 0),
        "rosterResolverRowsNoRosterMatch": sum(1 for row in enriched if "no_roster_evidence" in (row.get("playerTeamEvidenceWarnings") or [])),
        "sampleRosterCorrections": _samples(enriched, lambda row: bool(row.get("attributionCorrectionApplied")) and row.get("playerTeamEvidenceStatus") == "roster_match"),
        "sampleRosterVerified": _samples(enriched, lambda row: row.get("attributionStatus") == "verified" and row.get("playerTeamEvidenceStatus") == "verified"),
        "sampleRosterNoMatch": _samples(enriched, lambda row: "no_roster_evidence" in (row.get("playerTeamEvidenceWarnings") or [])),
        "sampleRosterAmbiguous": _samples(enriched, lambda row: row.get("attributionStatus") == "ambiguous"),
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
                "attributionCorrectionApplied": bool(row.get("attributionCorrectionApplied")),
                "playerTeamEvidenceStatus": _clean(row.get("playerTeamEvidenceStatus")),
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
