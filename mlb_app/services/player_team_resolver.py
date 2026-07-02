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


@dataclass
class SlateRosterIndex:
    """Roster/name evidence scoped to the teams appearing on one slate."""

    names_by_team: dict[str, set[str]] = field(default_factory=dict)
    teams_by_name: dict[str, set[str]] = field(default_factory=dict)

    def add_player(self, team: Any, player_name: Any) -> None:
        team_abbr = normalize_team_alias(team)
        if not team_abbr:
            return
        for name_key in player_name_variants(player_name):
            self.names_by_team.setdefault(team_abbr, set()).add(name_key)
            self.teams_by_name.setdefault(name_key, set()).add(team_abbr)

    def teams_for_player(self, player_name: Any, event_teams: list[str]) -> set[str]:
        event_team_set = {team for team in event_teams if team}
        matched: set[str] = set()
        for name_key in player_name_variants(player_name):
            matched.update(team for team in self.teams_by_name.get(name_key, set()) if team in event_team_set)
        return matched


_ROSTER_TEAM_BY_NAME: dict[str, str] = {
    "bobby witt": "KCR",
    "bobby witt jr": "KCR",
    "christian yelich": "MIL",
    "freddy peralta": "MIL",
    "jasson dominguez": "NYY",
    "jazz chisholm": "NYY",
    "jazz chisholm jr": "NYY",
    "jose altuve": "HOU",
    "paul skenes": "PIT",
    "trea turner": "PHI",
    "troy melton": "DET",
    "vladimir guerrero": "TOR",
    "vladimir guerrero jr": "TOR",
    "will warren": "NYY",
}

_ALIASES: dict[str, str] = {
    "bobby witt jr.": "bobby witt jr",
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


def player_name_variants(value: Any) -> set[str]:
    normalized = normalize_player_name(value)
    if not normalized:
        return set()
    variants = {normalized}
    tokens = normalized.split()
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    if len(tokens) > 2 and tokens[-1] in suffixes:
        variants.add(" ".join(tokens[:-1]))
    elif len(tokens) >= 2:
        # Common source rows sometimes omit suffixes while roster rows include them.
        for suffix in ("jr", "ii"):
            variants.add(f"{normalized} {suffix}")
    return variants


def resolve_player_team(
    *,
    player_name: Any,
    source_team: Any = "",
    source_opponent: Any = "",
    home_team: Any = "",
    away_team: Any = "",
    player_id: Any = "",
    roster_index: SlateRosterIndex | None = None,
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

    roster_team = ""
    sources = ["slate_roster_index"]
    if roster_index is not None and event_teams:
        matched_teams = roster_index.teams_for_player(name_key, event_teams)
        if len(matched_teams) > 1:
            return PlayerTeamResolution(status="ambiguous", sources=sources, warnings=["ambiguous_player_name"])
        if len(matched_teams) == 1:
            roster_team = next(iter(matched_teams))

    if not roster_team:
        roster_team = _ROSTER_TEAM_BY_NAME.get(name_key)
        sources = ["local_roster_seed"] if roster_team else sources

    if not roster_team:
        if source_team_abbr and source_opponent_abbr:
            return PlayerTeamResolution(
                status="missing",
                team_abbr=source_team_abbr,
                opponent_abbr=source_opponent_abbr,
                team=team_display_name(source_team_abbr),
                opponent=team_display_name(source_opponent_abbr),
                sources=sources if roster_index is not None else [],
                warnings=["no_roster_evidence"],
            )
        return PlayerTeamResolution(status="missing", warnings=["no_roster_evidence"])

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
