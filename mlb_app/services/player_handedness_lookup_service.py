from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import clean, first_value
from mlb_app.services.player_prop_context_identity_service import normalize_player_name, normalize_team


@dataclass(frozen=True)
class PlayerHandednessLookupResult:
    hand: str = ""
    source: str = ""
    sourceUpdatedAt: str = ""
    confidence: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    @property
    def batter_hand(self) -> str:
        return self.hand

    @property
    def throws_hand(self) -> str:
        return self.hand

    @property
    def pitcher_hand(self) -> str:
        return self.hand


@dataclass(frozen=True)
class _Candidate:
    player_id: str
    normalized_name: str
    normalized_team: str
    hand: str
    role: str
    source: str
    source_updated_at: str


class PlayerHandednessLookupService:
    """Deterministic local handedness lookup.

    This service is intentionally cache-only. It never calls external APIs and
    never infers handedness from a player's name.
    """

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        season: int | None = None,
        date_label: str | None = None,
    ) -> None:
        self.settings = settings
        self.season = season or settings.current_season
        self.date_label = date_label or ""
        self._loaded = False
        self._by_id: dict[tuple[str, str], list[_Candidate]] = defaultdict(list)
        self._by_name_team: dict[tuple[str, str, str], list[_Candidate]] = defaultdict(list)
        self._by_name: dict[tuple[str, str], list[_Candidate]] = defaultdict(list)
        self._player_index_by_id: dict[str, dict[str, str]] = {}

    def lookup(
        self,
        *,
        role: str,
        player_id: Any = "",
        player_name: Any = "",
        team: Any = "",
    ) -> PlayerHandednessLookupResult:
        self._load()
        lookup_role = _role_key(role)
        normalized_id = clean(player_id)
        normalized_name = normalize_player_name(player_name)
        normalized_team = normalize_team(team)

        if normalized_id:
            result = self._resolve_candidates(
                self._by_id.get((lookup_role, normalized_id), []),
                confidence="high",
                warning_prefix="id",
            )
            if result.hand or result.warnings:
                return result

        if normalized_name and normalized_team:
            result = self._resolve_candidates(
                self._by_name_team.get((lookup_role, normalized_name, normalized_team), []),
                confidence="high",
                warning_prefix="name_team",
            )
            if result.hand or result.warnings:
                return result

        if normalized_name:
            candidates = self._by_name.get((lookup_role, normalized_name), [])
            teams = {candidate.normalized_team for candidate in candidates if candidate.normalized_team}
            ids = {candidate.player_id for candidate in candidates if candidate.player_id}
            if len(teams) > 1 or len(ids) > 1:
                return PlayerHandednessLookupResult(
                    warnings=[f"ambiguous_{lookup_role}_hand_name_only_match"],
                )
            result = self._resolve_candidates(candidates, confidence="medium", warning_prefix="name")
            if result.hand or result.warnings:
                return result

        return PlayerHandednessLookupResult(warnings=[f"{lookup_role}_hand_not_found"])

    def _resolve_candidates(
        self,
        candidates: list[_Candidate],
        *,
        confidence: str,
        warning_prefix: str,
    ) -> PlayerHandednessLookupResult:
        if not candidates:
            return PlayerHandednessLookupResult()
        hands = {candidate.hand for candidate in candidates if candidate.hand}
        if len(hands) != 1:
            return PlayerHandednessLookupResult(warnings=[f"ambiguous_{warning_prefix}_hand_conflict"])
        hand = next(iter(hands))
        source_counts = Counter(candidate.source for candidate in candidates if candidate.hand == hand)
        source = source_counts.most_common(1)[0][0] if source_counts else candidates[-1].source
        updated = ""
        for candidate in reversed(candidates):
            if candidate.source == source and candidate.source_updated_at:
                updated = candidate.source_updated_at
                break
        return PlayerHandednessLookupResult(
            hand=hand,
            source=source,
            sourceUpdatedAt=updated,
            confidence=confidence,
            warnings=[],
        )

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._load_player_index()
        self._load_game_logs("batter", self._cache_path("batter_game_logs"), ("bats", "stand", "batter_hand"))
        self._load_game_logs("pitcher", self._cache_path("pitcher_game_logs"), ("throws", "p_throws", "pitcher_hand"))
        self._load_game_logs("batter", self._season_log_path("batter_game_logs"), ("bats", "stand", "batter_hand"))
        self._load_game_logs("pitcher", self._season_log_path("pitcher_game_logs"), ("throws", "p_throws", "pitcher_hand"))
        self._load_statcast()

    def _load_player_index(self) -> None:
        path = self._cache_path("player_index")
        if not path.is_file():
            return
        for row in _read_rows(path):
            player_id = clean(row.get("playerId"))
            if player_id:
                self._player_index_by_id[player_id] = row

    def _load_game_logs(self, role: str, path: Path, hand_aliases: tuple[str, ...]) -> None:
        if not path.is_file():
            return
        source = str(path)
        updated = _source_updated_at(path)
        for row in _read_rows(path):
            if not _is_before_target(row, self.date_label):
                continue
            hand = _normalized_hand(first_value(row, list(hand_aliases)))
            if not hand:
                continue
            self._add_candidate(
                role=role,
                player_id=first_value(row, ["playerId", "mlbam_id", "player_mlbam_id"]),
                player_name=first_value(row, ["player", "playerName", "name"]),
                team=first_value(row, ["team", "teamAbbr", "team_abbr"]),
                hand=hand,
                source=source,
                source_updated_at=updated,
            )

    def _load_statcast(self) -> None:
        for path in self._statcast_paths():
            source = str(path)
            updated = _source_updated_at(path)
            for row in _read_rows(path):
                if not _is_before_target(row, self.date_label, aliases=("game_date", "date", "gameDate")):
                    continue
                batter_id = clean(first_value(row, ["batter", "batter_id", "player_mlbam_id"]))
                batter_meta = self._player_index_by_id.get(batter_id, {})
                self._add_candidate(
                    role="batter",
                    player_id=batter_id,
                    player_name=first_value(row, ["batter_name", "player", "name"]) or batter_meta.get("player", ""),
                    team=_batter_team(row) or batter_meta.get("team", ""),
                    hand=_normalized_hand(first_value(row, ["stand", "batter_hand"])),
                    source=source,
                    source_updated_at=updated,
                )
                self._add_candidate(
                    role="pitcher",
                    player_id=first_value(row, ["pitcher", "pitcher_id", "pitcher_mlbam_id"]),
                    player_name=_normal_name(clean(first_value(row, ["player_name", "pitcher_name", "pitcherPlayerName"]))),
                    team="",
                    hand=_normalized_hand(first_value(row, ["p_throws", "throws", "pitcher_hand"])),
                    source=source,
                    source_updated_at=updated,
                )

    def _add_candidate(
        self,
        *,
        role: str,
        player_id: Any,
        player_name: Any,
        team: Any,
        hand: Any,
        source: str,
        source_updated_at: str,
    ) -> None:
        normalized_hand = _normalized_hand(hand)
        if normalized_hand not in {"L", "R", "S"}:
            return
        candidate = _Candidate(
            player_id=clean(player_id),
            normalized_name=normalize_player_name(player_name),
            normalized_team=normalize_team(team),
            hand=normalized_hand,
            role=_role_key(role),
            source=source,
            source_updated_at=source_updated_at,
        )
        if not candidate.player_id and not candidate.normalized_name:
            return
        if candidate.player_id:
            self._by_id[(candidate.role, candidate.player_id)].append(candidate)
        if candidate.normalized_name and candidate.normalized_team:
            self._by_name_team[(candidate.role, candidate.normalized_name, candidate.normalized_team)].append(candidate)
        if candidate.normalized_name:
            self._by_name[(candidate.role, candidate.normalized_name)].append(candidate)

    def _cache_path(self, stem: str) -> Path:
        return self.settings.data_dir / "cache" / "incremental_stats" / f"{stem}_{self.season}.csv"

    def _season_log_path(self, stem: str) -> Path:
        warehouse = self.settings.data_dir / "warehouse" / "season_logs" / f"{stem}_{self.season}.csv"
        cloud = self.settings.data_dir / "cloud" / "season_logs" / f"{stem}_{self.season}.csv"
        return warehouse if warehouse.is_file() else cloud

    def _statcast_paths(self) -> list[Path]:
        return [
            self.settings.data_dir / "warehouse" / "statcast" / f"statcast_{self.season}.csv",
            self.settings.data_dir / "cache" / "statcast" / f"statcast_{self.season}.csv",
            *sorted((self.settings.data_dir / "cache" / "savant").glob(f"statcast_{self.season}_*.csv")),
            *sorted((self.settings.data_dir / "cache" / "savant" / "raw").glob(f"statcast_{self.season}_*.csv")),
        ]


def _read_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def _is_before_target(
    row: dict[str, Any],
    target_label: str,
    *,
    aliases: tuple[str, ...] = ("date", "game_date", "gameDate"),
) -> bool:
    if not target_label:
        return True
    raw = clean(first_value(row, list(aliases)))
    try:
        row_date = date.fromisoformat(raw[:10])
        target = date.fromisoformat(target_label)
    except ValueError:
        return False
    return row_date < target


def _normalized_hand(value: Any) -> str:
    text = clean(value).upper()
    if text in {"L", "LEFT", "LHP"}:
        return "L"
    if text in {"R", "RIGHT", "RHP"}:
        return "R"
    if text in {"S", "B", "SWITCH"}:
        return "S"
    return ""


def _normal_name(value: str) -> str:
    if "," in value:
        last, first = [part.strip() for part in value.split(",", 1)]
        return f"{first} {last}".strip()
    return value


def _batter_team(row: dict[str, Any]) -> str:
    half = clean(first_value(row, ["inning_topbot"])).lower()
    if half.startswith("top"):
        return clean(first_value(row, ["away_team", "awayTeam"]))
    if half.startswith("bot"):
        return clean(first_value(row, ["home_team", "homeTeam"]))
    return clean(first_value(row, ["team", "bat_team", "batting_team"]))


def _source_updated_at(path: Path) -> str:
    try:
        return date.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""


def _role_key(value: Any) -> str:
    text = clean(value).lower()
    return "pitcher" if text == "pitcher" else "batter"
