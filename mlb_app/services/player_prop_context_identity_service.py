from __future__ import annotations

import re
import unicodedata
from typing import Any

from mlb_app.services.player_prop_model_runtime import first_value, model_market_key
from mlb_app.services.team_match_utils import normalize_team_alias

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PLAYER_DESCRIPTION_SUFFIXES = (
    "Strikeouts Thrown",
    "Pitcher Strikeouts",
    "Hits Allowed",
    "Earned Runs",
    "Stolen Bases",
    "Total Bases",
    "Home Runs",
    "Strikeouts",
    "Doubles",
    "Singles",
    "Walks",
    "RBIs",
    "Runs",
    "Hits",
)
_PITCHER_MARKETS = {
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
    "pitcher_walks_allowed",
    "pitcher_outs",
}
_BATTER_MARKET_PREFIXES = ("batter_", "hitter_")
_MARKET_SUFFIXES = {
    "pitcher_strikeouts": ("Strikeouts Thrown", "Pitcher Strikeouts"),
    "pitcher_hits_allowed": ("Hits Allowed",),
    "pitcher_earned_runs": ("Earned Runs",),
    "batter_hits": ("Hits",),
    "batter_total_bases": ("Total Bases",),
    "batter_home_runs": ("Home Runs",),
    "batter_rbis": ("RBIs",),
    "batter_runs": ("Runs",),
    "batter_stolen_bases": ("Stolen Bases",),
}


def normalize_player_name(value: Any) -> str:
    """Return a deterministic player-name key without fuzzy matching."""

    text = str(value or "").strip()
    if not text:
        return ""
    text = _strip_descriptive_suffix(text)
    if "," in text:
        last, first = [part.strip() for part in text.split(",", 1)]
        if first.rstrip(".").casefold() in _SUFFIXES:
            text = last
        else:
            text = f"{first} {last}".strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("'", "").replace("`", "")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    parts = [part.casefold() for part in text.split() if part.strip()]
    while parts and parts[-1].rstrip(".").casefold() in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def normalize_pitcher_name(value: Any) -> str:
    return normalize_player_name(value)


def normalize_team(value: Any) -> str:
    return normalize_team_alias(value)


def normalize_opponent(value: Any) -> str:
    return normalize_team(value)


def normalize_book_key(value: Any) -> str:
    return _simple_key(value)


def normalize_market_key(value: Any) -> str:
    return model_market_key(value)


def subject_role_for_market(value: Any) -> str:
    market = normalize_market_key(value)
    if market in _PITCHER_MARKETS or market.startswith("pitcher_"):
        return "pitcher"
    if market.startswith(_BATTER_MARKET_PREFIXES):
        return "batter"
    return "unknown"


def clean_subject_name(value: Any, market: Any) -> tuple[str, list[str]]:
    """Clean only market-confirmed prop suffixes from a display subject."""

    original = str(value or "").strip()
    if not original:
        return "", []
    cleaned = original
    market_key = normalize_market_key(market)
    for suffix in _MARKET_SUFFIXES.get(market_key, ()):
        pattern = rf"\s+(?:\d+(?:\.\d+)?\+?\s+)?{re.escape(suffix)}$"
        candidate = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        if candidate != cleaned and _looks_like_player_name(candidate):
            cleaned = candidate
            break
    warnings = ["subject_name_cleaned_from_market_label"] if cleaned != original else []
    return cleaned, warnings


def align_board_context_identity(row: dict[str, Any]) -> dict[str, Any]:
    """Return subject identity fields for safe board-to-context joins."""

    aligned = dict(row)
    market = first_value(aligned, ["market", "baseMarket"], "")
    role = subject_role_for_market(market)
    display_name = str(
        first_value(
            aligned,
            [
                "subjectName",
                "subject_name",
                "player",
                "playerName",
                "name",
                "label",
                "title",
                "outcome",
                "outcomeName",
                "selection",
            ],
            "",
        )
        or ""
    ).strip()
    if role == "pitcher":
        display_name = str(
            first_value(
                aligned,
                ["subjectName", "subject_name", "pitcher", "player", "playerName", "name"],
                display_name,
            )
            or ""
        ).strip()
    cleaned_name, warnings = clean_subject_name(display_name, market)
    normalized_name = normalize_player_name(cleaned_name)
    subject_team, subject_opponent, team_warnings, fixed_reversed, suspected_reversed = _aligned_subject_sides(aligned)
    warnings.extend(team_warnings)
    aligned.update(
        {
            "subjectDisplayName": display_name,
            "subjectName": cleaned_name,
            "normalizedSubjectName": normalized_name,
            "subjectRole": role,
            "subjectNameSource": _subject_name_source(aligned, role),
            "subjectTeam": subject_team,
            "subjectOpponent": subject_opponent,
            "normalizedSubjectTeam": normalize_team(subject_team),
            "normalizedSubjectOpponent": normalize_opponent(subject_opponent),
            "subjectIdentityWarnings": "|".join(sorted(set(warnings))),
            "subjectTeamOpponentFixed": fixed_reversed,
            "subjectTeamOpponentSuspectedReversed": suspected_reversed,
        }
    )
    return aligned


def _simple_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _aligned_subject_sides(row: dict[str, Any]) -> tuple[str, str, list[str], bool, bool]:
    warnings: list[str] = []
    explicit_subject_team = normalize_team(
        first_value(
            row,
            ["subjectTeam", "subject_team", "playerTeam", "player_team", "participantTeam", "participant_team"],
            "",
        )
    )
    raw_team = normalize_team(first_value(row, ["team", "teamAbbr", "team_abbr", "teamCode"], ""))
    raw_opponent = normalize_opponent(first_value(row, ["opponent", "opponentAbbr", "opponent_abbr", "opponentCode"], ""))
    home = normalize_team(first_value(row, ["homeTeam", "home_team", "home"], ""))
    away = normalize_team(first_value(row, ["awayTeam", "away_team", "away"], ""))
    subject_team = explicit_subject_team or raw_team
    subject_opponent = raw_opponent
    fixed_reversed = False
    suspected_reversed = False

    if (
        explicit_subject_team
        and raw_team
        and raw_opponent
        and raw_team != explicit_subject_team
        and raw_opponent == explicit_subject_team
    ):
        subject_team = raw_opponent
        subject_opponent = raw_team
        fixed_reversed = True
        warnings.append("team_opponent_reversed_fixed_from_explicit_subject_team")
    elif explicit_subject_team and raw_team and raw_team != explicit_subject_team:
        suspected_reversed = True
        warnings.append("team_opponent_mismatch")

    if subject_team and not subject_opponent and home and away:
        if subject_team == home:
            subject_opponent = away
        elif subject_team == away:
            subject_opponent = home
        else:
            warnings.append("skipped_unsafe_team_inference")
    elif not subject_team and home and away:
        warnings.append("skipped_unsafe_team_inference")

    if subject_team and subject_opponent and subject_team == subject_opponent:
        warnings.append("subject_team_matches_opponent")
        subject_opponent = ""
    if not subject_team:
        warnings.append("missing_subject_team")
    if not subject_opponent:
        warnings.append("missing_subject_opponent")
    return subject_team, subject_opponent, warnings, fixed_reversed, suspected_reversed


def _subject_name_source(row: dict[str, Any], role: str) -> str:
    aliases = ["subjectName", "subject_name"]
    if role == "pitcher":
        aliases.extend(["pitcher", "player", "playerName", "name"])
    else:
        aliases.extend(["player", "playerName", "name"])
    for alias in aliases:
        if str(first_value(row, [alias], "") or "").strip():
            return alias
    return "unknown"


def _strip_descriptive_suffix(value: str) -> str:
    side_match = re.search(r"\s+(?:Over|Under)\b", value, flags=re.IGNORECASE)
    if side_match:
        candidate = value[: side_match.start()].strip()
        if _looks_like_player_name(candidate):
            return candidate

    for suffix in _PLAYER_DESCRIPTION_SUFFIXES:
        pattern = rf"\s+(?:\d+(?:\.\d+)?\+?\s+)?{re.escape(suffix)}$"
        candidate = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
        if candidate != value and _looks_like_player_name(candidate):
            return candidate
    return value


def _looks_like_player_name(value: str) -> bool:
    tokens = re.findall(r"[A-Za-z][A-Za-z'.-]*", value)
    return len(tokens) >= 2
