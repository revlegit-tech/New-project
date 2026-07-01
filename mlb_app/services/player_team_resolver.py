from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from mlb_app.services.team_match_utils import normalize_team_alias, team_display_name


@dataclass(frozen=True)
class PlayerTeamResolution:
    status: str = "missing"
    team_abbr: str = ""
    opponent_abbr: str = ""
    team: str = ""
    opponent: str = ""
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def verified(self) -> bool:
        return self.status in {"verified", "roster_match", "game_log_match", "source_match"}


_ROSTER_TEAM_BY_NAME: dict[str, str] = {
    "freddy peralta": "MIL",
    "jasson dominguez": "NYY",
    "jazz chisholm": "NYY",
    "jazz chisholm jr": "NYY",
    "paul skenes": "PIT",
    "troy melton": "DET",
    "vladimir guerrero": "TOR",
    "vladimir guerrero jr": "TOR",
    "will warren": "NYY",
}

_ALIASES: dict[str, str] = {
    "jazz chisholm jr.": "jazz chisholm jr",
    "vladimir guerrero jr.": "vladimir guerrero jr",
    "vladdy guerrero": "vladimir guerrero jr",
    "vladdy guerrero jr": "vladimir guerrero jr",
}

_AMBIGUOUS_NAMES = {
    "luis garcia",
}


def normalize_player_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().replace(".", " ")
    tokens = []
    for token in text.replace("-", " ").split():
        cleaned = "".join(char for char in token if char.isalnum())
        if cleaned:
            tokens.append(cleaned)
    normalized = " ".join(tokens)
    return _ALIASES.get(normalized, normalized)


def resolve_player_team(
    *,
    player_name: Any,
    source_team: Any = "",
    source_opponent: Any = "",
    home_team: Any = "",
    away_team: Any = "",
    player_id: Any = "",
) -> PlayerTeamResolution:
    del player_id
    name_key = normalize_player_name(player_name)
    source_team_abbr = normalize_team_alias(source_team)
    source_opponent_abbr = normalize_team_alias(source_opponent)
    event_teams = _event_teams(source_team_abbr, source_opponent_abbr, home_team, away_team)

    if not name_key:
        return PlayerTeamResolution(status="missing", warnings=["missing_player_name"])
    if name_key in _AMBIGUOUS_NAMES:
        return PlayerTeamResolution(status="ambiguous", sources=["local_roster_seed"], warnings=["ambiguous_player_name"])

    roster_team = _ROSTER_TEAM_BY_NAME.get(name_key)
    if not roster_team:
        if source_team_abbr and source_opponent_abbr:
            return PlayerTeamResolution(
                status="inferred",
                team_abbr=source_team_abbr,
                opponent_abbr=source_opponent_abbr,
                team=team_display_name(source_team_abbr),
                opponent=team_display_name(source_opponent_abbr),
                warnings=["no_roster_evidence"],
            )
        return PlayerTeamResolution(status="missing", warnings=["no_roster_evidence"])

    sources = ["local_roster_seed"]
    if len(event_teams) < 2:
        return PlayerTeamResolution(
            status="missing",
            team_abbr=roster_team,
            team=team_display_name(roster_team),
            sources=sources,
            warnings=["missing_event_context"],
        )
    if event_teams and roster_team not in event_teams:
        return PlayerTeamResolution(
            status="conflict",
            team_abbr=roster_team,
            team=team_display_name(roster_team),
            sources=sources,
            warnings=["roster_team_not_in_event"],
            reason=f"roster_team_not_in_event:{roster_team}",
        )

    opponent = _opponent_for(roster_team, event_teams, source_team_abbr, source_opponent_abbr)
    if source_team_abbr == roster_team:
        status = "verified"
        reason = "source_team_matches_roster"
    elif source_team_abbr and source_team_abbr != roster_team:
        status = "roster_match"
        reason = "source_team_mismatch_corrected"
    else:
        status = "roster_match"
        reason = "team_verified_by_roster"

    return PlayerTeamResolution(
        status=status,
        team_abbr=roster_team,
        opponent_abbr=opponent,
        team=team_display_name(roster_team),
        opponent=team_display_name(opponent) if opponent else "",
        sources=sources,
        warnings=[],
        reason=reason,
    )


def _event_teams(source_team: str, source_opponent: str, home_team: Any, away_team: Any) -> list[str]:
    teams = [
        normalize_team_alias(away_team),
        normalize_team_alias(home_team),
        source_team,
        source_opponent,
    ]
    out: list[str] = []
    for team in teams:
        if team and team not in out:
            out.append(team)
    return out[:2] if len(out) >= 2 else out


def _opponent_for(team: str, event_teams: list[str], source_team: str, source_opponent: str) -> str:
    for candidate in event_teams:
        if candidate and candidate != team:
            return candidate
    if source_team == team:
        return source_opponent
    if source_opponent == team:
        return source_team
    return ""
