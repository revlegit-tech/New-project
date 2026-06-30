from __future__ import annotations

from typing import Any

from mlb_app.services.prop_side_normalization import normalize_prop_side

IDENTITY_CONTEXT_WARNING = "Identity is inferred from board context. Research only."


def identity_confidence_for_row(row: dict[str, Any], *, input_source: str = "") -> dict[str, Any]:
    player = _clean(_first(row, "player", "playerName", "name"))
    market = _clean(_first(row, "market", "baseMarket"))
    side = normalize_prop_side(
        _first(row, "side"),
        _first(row, "rawLabel", "raw_label"),
        _first(row, "label", "title", "name"),
        _first(row, "outcome", "outcomeName", "outcome_name", "selection", "pickSide"),
    )
    line = _clean(_first(row, "line", "sportsbook_line", "prop_line"))
    team = _clean(_first(row, "team", "team_abbr", "teamCode", "away", "away_team", "awayTeam"))
    opponent = _clean(_first(row, "opponent", "opponent_abbr", "opponentCode", "home", "home_team", "homeTeam"))
    player_team_verified = _truthy(_first(row, "playerTeamVerified", "player_team_verified", "player_team_is_verified"))
    opponent_verified = _truthy(_first(row, "opponentVerified", "opponent_verified", "opponent_is_verified"))

    has_feature_identity = True
    if input_source == "features":
        has_feature_identity = all(_clean(_first(row, key, _camel(key))) for key in ("source_row_id", "prop_key", "game_pk"))
        player_team_verified = player_team_verified or (has_feature_identity and bool(team))
        opponent_verified = opponent_verified or (has_feature_identity and bool(opponent))

    core_complete = all([player, market, side, line])
    warnings: list[str] = []
    if input_source == "features" and not has_feature_identity:
        warnings.append("unsafe_prediction_join_key")
        confidence = "unknown"
    elif not core_complete:
        missing = [
            name
            for name, value in (("player", player), ("market", market), ("side", side), ("line", line))
            if not value
        ]
        warnings.append(f"insufficient_identity_information:{','.join(missing)}")
        confidence = "unknown"
    elif team and opponent and player_team_verified and opponent_verified:
        confidence = "strong"
    elif team and opponent:
        confidence = "medium"
        warnings.append(IDENTITY_CONTEXT_WARNING)
    else:
        confidence = "weak"
        if not team and not opponent:
            warnings.append("missing_team_and_opponent_identity")
        elif not team:
            warnings.append("missing_player_team_identity")
        else:
            warnings.append("missing_opponent_identity")

    return {
        "identityConfidence": confidence,
        "identityWarnings": warnings,
        "playerTeamVerified": bool(player_team_verified),
        "opponentVerified": bool(opponent_verified),
    }


def parse_identity_warnings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    if not text:
        return []
    separators = "|" if "|" in text else ";"
    return [_clean(part) for part in text.split(separators) if _clean(part)]


def serialize_identity_warnings(value: Any) -> str:
    return "|".join(parse_identity_warnings(value))


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


def _camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
