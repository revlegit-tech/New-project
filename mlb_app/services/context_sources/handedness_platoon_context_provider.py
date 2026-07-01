from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import (
    ContextProviderResult,
    clean,
    context_path,
    first_value,
    read_csv_rows,
    status_for_rows,
    to_float,
    write_csv_rows,
)
from mlb_app.services.player_prop_context_identity_service import (
    align_board_context_identity,
    normalize_opponent,
    normalize_player_name,
    normalize_team,
)


HAND_PLATOON_FIELDS = [
    "date",
    "season",
    "player",
    "team",
    "opponent",
    "normalizedPlayer",
    "normalizedTeam",
    "normalizedOpponent",
    "subjectRole",
    "batter_hand",
    "pitcher_hand",
    "batter_avg_vs_hand",
    "batter_k_rate_vs_hand",
    "batter_recent_hits_vs_lhp",
    "batter_recent_hits_vs_rhp",
    "pitcher_avg_allowed_vs_hand",
    "source",
    "sourceUpdatedAt",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
    "seedSource",
    "seedMarketCount",
    "seedRowCount",
    "seedSubjectNameSource",
    "enrichmentStatus",
]


class HandednessPlatoonContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "handedness_platoon", f"handedness_platoon_{date_label}.csv")
        batter_path = self._batter_log_path(season)
        pitcher_path = self._pitcher_log_path(season)
        warnings: list[str] = []
        seed_rows, seed_diagnostics = self._seed_rows(date_label=date_label, season=season)
        if not seed_rows:
            warnings.append("No current board batter subjects available; handedness/platoon context unavailable.")
            write_csv_rows(output_path, [], HAND_PLATOON_FIELDS)
            diagnostics = self._diagnostics(date_label, season, seed_diagnostics, [], [])
            return self._result("missing", date_label, season, 0, output_path, warnings, diagnostics)

        batter_rows = _pregame_rows(read_csv_rows(batter_path), date_label) if batter_path.is_file() else []
        pitcher_rows = _pregame_rows(read_csv_rows(pitcher_path), date_label) if pitcher_path.is_file() else []
        if not batter_path.is_file():
            warnings.append("Local batter game log not found; handedness and split fields left null.")
        if not pitcher_path.is_file():
            warnings.append("Local pitcher game log not found; pitcher_hand and pitcher splits left null.")
        if batter_rows and not _has_any_column(batter_rows, ["bats", "stand", "batter_hand"]):
            warnings.append("Known batter handedness mappings unavailable; batter_hand left null.")
        if pitcher_rows and not _has_any_column(pitcher_rows, ["throws", "p_throws", "pitcher_hand"]):
            warnings.append("Known pitcher handedness mappings unavailable; pitcher_hand left null.")

        batter_rows_by_player = _batter_rows_by_player_team(batter_rows)
        pitcher_hand_by_name = _latest_pitcher_hand_by_name(pitcher_rows)
        pitcher_avg_allowed = _pitcher_avg_allowed_by_name(pitcher_rows)
        generated_at = datetime.now(timezone.utc).isoformat()
        output = [
            _platoon_summary(
                date_label,
                season,
                seed,
                batter_rows_by_player.get((seed["normalizedPlayer"], seed["normalizedTeam"])) or [],
                pitcher_hand_by_name,
                pitcher_avg_allowed,
                batter_path if batter_path.is_file() else Path(""),
                generated_at,
            )
            for seed in seed_rows
        ]
        if not output:
            warnings.append("No current board batter context rows generated.")
        for row in output:
            row_warnings = []
            if not row.get("batter_hand") and "missing batter history" in str(row.get("enrichmentStatus", "")):
                row_warnings.append("batter history unavailable")
            if not row.get("batter_hand"):
                row_warnings.append("batter_hand unknown")
            if not row.get("pitcher_hand"):
                row_warnings.append("pitcher_hand unknown")
            if not _has_any_split_stat(row):
                row_warnings.append("split stats unavailable")
            row["warnings"] = "; ".join(row_warnings)
        write_csv_rows(output_path, output, HAND_PLATOON_FIELDS)
        diagnostics = self._diagnostics(date_label, season, seed_diagnostics, output, seed_rows)
        return self._result(status_for_rows(len(output), warnings), date_label, season, len(output), output_path, warnings, diagnostics)

    def _batter_log_path(self, season: int) -> Path:
        cloud = self.settings.data_dir / "cloud" / "season_logs" / f"batter_game_logs_{season}.csv"
        warehouse = self.settings.data_dir / "warehouse" / "season_logs" / f"batter_game_logs_{season}.csv"
        return warehouse if warehouse.is_file() else cloud

    def _pitcher_log_path(self, season: int) -> Path:
        cloud = self.settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        warehouse = self.settings.data_dir / "warehouse" / "season_logs" / f"pitcher_game_logs_{season}.csv"
        return warehouse if warehouse.is_file() else cloud

    def _seed_rows(self, *, date_label: str, season: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        seed_path = self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv"
        source_mode = "playerboard"
        raw_rows = _read_date_rows(seed_path, date_label)
        if not raw_rows:
            seed_path = self.settings.data_dir / "odds" / f"propline_props_{date_label}.csv"
            source_mode = "propline_props"
            raw_rows = _read_date_rows(seed_path, date_label, date_aliases=("eventDateLocal", "date"))

        diagnostics: dict[str, Any] = {
            "providerSourceMode": source_mode if raw_rows else "none",
            "providerSeedPath": str(seed_path),
            "providerSeedRows": len(raw_rows),
            "providerSeedDate": date_label,
            "providerSeedSlateMatchesTargetDate": bool(raw_rows),
            "boardSeedRows": len(raw_rows) if source_mode == "playerboard" else 0,
            "boardSeedBatterRows": 0,
            "boardSeedPitcherRows": 0,
            "boardSeedSkippedRows": 0,
            "boardSeedSkipReasons": {},
        }
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        skip_reasons: defaultdict[str, int] = defaultdict(int)
        batter_rows = 0
        pitcher_rows = 0
        for raw in raw_rows:
            aligned = align_board_context_identity(raw)
            role = clean(aligned.get("subjectRole")).lower() or "unknown"
            if role == "pitcher":
                pitcher_rows += 1
                skip_reasons["role_not_applicable"] += 1
                continue
            if role != "batter":
                skip_reasons["role_not_batter"] += 1
                continue
            batter_rows += 1
            player = clean(aligned.get("subjectName"))
            normalized_player = clean(aligned.get("normalizedSubjectName")) or normalize_player_name(player)
            team = clean(aligned.get("subjectTeam"))
            opponent = clean(aligned.get("subjectOpponent"))
            normalized_team = clean(aligned.get("normalizedSubjectTeam")) or normalize_team(team)
            normalized_opponent = clean(aligned.get("normalizedSubjectOpponent")) or normalize_opponent(opponent)
            if not normalized_player:
                skip_reasons["missing_subject_identity"] += 1
                continue
            if not normalized_team:
                skip_reasons["missing_subject_team"] += 1
                continue
            if not normalized_opponent:
                skip_reasons["missing_subject_opponent"] += 1
                continue
            seed_key = (normalized_player, normalized_team, normalized_opponent)
            seed = deduped.setdefault(
                seed_key,
                {
                    "player": player,
                    "team": team or normalized_team,
                    "opponent": opponent or normalized_opponent,
                    "normalizedPlayer": normalized_player,
                    "normalizedTeam": normalized_team,
                    "normalizedOpponent": normalized_opponent,
                    "subjectRole": "batter",
                    "pitcher": clean(first_value(aligned, ["pitcher", "probablePitcher", "probable_pitcher"])),
                    "seedSource": source_mode,
                    "seedMarketCount": 0,
                    "seedRowCount": 0,
                    "seedSubjectNameSource": clean(aligned.get("subjectNameSource")),
                },
            )
            seed["seedMarketCount"] = len(
                set(
                    str(value).strip()
                    for value in [seed.get("markets", ""), clean(first_value(aligned, ["market", "baseMarket"]))]
                    if str(value).strip()
                )
            )
            seed["seedRowCount"] = int(seed.get("seedRowCount") or 0) + 1
            market = clean(first_value(aligned, ["market", "baseMarket"]))
            if market:
                markets = set(str(seed.get("markets") or "").split("|")) if seed.get("markets") else set()
                markets.add(market)
                seed["markets"] = "|".join(sorted(markets))
                seed["seedMarketCount"] = len(markets)

        diagnostics["providerSeedBatterRows"] = batter_rows
        diagnostics["providerSeedPitcherRows"] = pitcher_rows
        diagnostics["boardSeedBatterRows"] = batter_rows if source_mode == "playerboard" else 0
        diagnostics["boardSeedPitcherRows"] = pitcher_rows if source_mode == "playerboard" else 0
        diagnostics["boardSeedSkippedRows"] = sum(skip_reasons.values())
        diagnostics["boardSeedSkipReasons"] = dict(sorted(skip_reasons.items()))
        diagnostics["contextRowsDeduped"] = max(batter_rows - len(deduped), 0)
        return list(deduped.values()), diagnostics

    def _diagnostics(
        self,
        date_label: str,
        season: int,
        seed_diagnostics: dict[str, Any],
        output: list[dict[str, Any]],
        seed_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        seed_keys = {_context_key(seed, date_label, season) for seed in seed_rows}
        output_keys = {_context_key(row, date_label, season) for row in output}
        not_on_board = [row for row in output if _context_key(row, date_label, season) not in seed_keys]
        without_context = [seed for seed in seed_rows if _context_key(seed, date_label, season) not in output_keys]
        with_split_stats = [row for row in output if _has_any_split_stat(row)]
        diagnostics = {
            **seed_diagnostics,
            "contextRowsGenerated": len(output),
            "contextRowsGeneratedFromBoard": len(output) if seed_diagnostics.get("providerSourceMode") == "playerboard" else 0,
            "contextRowsMatchingBoardSubjects": len(output_keys.intersection(seed_keys)),
            "contextRowsNotOnBoardSlate": len(not_on_board),
            "boardBatterSubjectsWithoutContextRows": len(without_context),
            "contextRowsWithBatterHand": sum(1 for row in output if clean(row.get("batter_hand"))),
            "contextRowsWithPitcherHand": sum(1 for row in output if clean(row.get("pitcher_hand"))),
            "contextRowsWithSplitStats": len(with_split_stats),
            "externalApiCallsMade": 0,
            "pregameSafe": True,
            "labelsExcluded": True,
            "warnings": sorted({warning for row in output for warning in str(row.get("warnings") or "").split("; ") if warning}),
            "sampleBoardBatterWithoutContext": [_sample(seed) for seed in without_context[:10]],
            "sampleContextNotOnBoard": [_sample(row) for row in not_on_board[:10]],
            "sampleRowsMissingHandedness": [_sample(row) for row in output if not clean(row.get("batter_hand"))][:10],
        }
        diagnostics["boardBatterRowsWithoutContext"] = diagnostics["boardBatterSubjectsWithoutContextRows"]
        diagnostics["contextRowsNotOnBoard"] = diagnostics["contextRowsNotOnBoardSlate"]
        return diagnostics

    def _result(
        self,
        status: str,
        date_label: str,
        season: int,
        rows: int,
        path: Path,
        warnings: list[str],
        diagnostics: dict[str, Any],
    ) -> ContextProviderResult:
        return ContextProviderResult(
            status=status,
            date=date_label,
            season=season,
            source="handedness_platoon",
            rows=rows,
            path=str(path),
            warnings=warnings,
            diagnostics=diagnostics,
        )


def _pregame_rows(rows: list[dict[str, str]], date_label: str) -> list[dict[str, str]]:
    try:
        target = date.fromisoformat(date_label)
    except ValueError:
        return []
    output: list[dict[str, str]] = []
    for row in rows:
        raw = clean(first_value(row, ["date", "game_date", "gameDate"]))
        try:
            row_date = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if row_date < target:
            output.append(row)
    return output


def _batter_rows_by_player_team(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        player = clean(first_value(row, ["player", "playerName", "name"]))
        team = clean(first_value(row, ["team", "teamAbbr"]))
        normalized_player = normalize_player_name(player)
        normalized_team = normalize_team(team)
        if normalized_player and normalized_team:
            grouped[(normalized_player, normalized_team)].append(row)
    return {group_key: sorted(value, key=lambda row: clean(first_value(row, ["date", "game_date", "gameDate"]))) for group_key, value in grouped.items()}


def _platoon_summary(
    date_label: str,
    season: int,
    seed: dict[str, Any],
    rows: list[dict[str, str]],
    pitcher_hand_by_name: dict[str, str],
    pitcher_avg_allowed: dict[tuple[str, str], float | str],
    source: Path,
    generated_at: str,
) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    player = clean(seed.get("player"))
    team = clean(seed.get("team"))
    opponent = clean(seed.get("opponent"))
    pitcher_name = clean(seed.get("pitcher"))
    normalized_pitcher = normalize_player_name(pitcher_name)
    pitcher_hand = pitcher_hand_by_name.get(normalized_pitcher, "") if normalized_pitcher else ""
    split_rows = [row for row in rows if _normalized_hand(first_value(row, ["pitcher_hand", "p_throws", "throws"])) == pitcher_hand]
    lhp_rows = [row for row in rows[-10:] if _normalized_hand(first_value(row, ["pitcher_hand", "p_throws", "throws"])) == "L"]
    rhp_rows = [row for row in rows[-10:] if _normalized_hand(first_value(row, ["pitcher_hand", "p_throws", "throws"])) == "R"]
    batter_hand = _normalized_hand(first_value(latest, ["bats", "stand", "batter_hand"])) if latest else ""
    enrichment_status = []
    if not rows:
        enrichment_status.append("missing batter history")
    if not batter_hand:
        enrichment_status.append("missing batter_hand")
    if not pitcher_hand:
        enrichment_status.append("missing pitcher_hand")
    return {
        "date": date_label,
        "season": season,
        "player": player,
        "team": team,
        "opponent": opponent,
        "normalizedPlayer": clean(seed.get("normalizedPlayer")) or normalize_player_name(player),
        "normalizedTeam": clean(seed.get("normalizedTeam")) or normalize_team(team),
        "normalizedOpponent": clean(seed.get("normalizedOpponent")) or normalize_opponent(opponent),
        "subjectRole": "batter",
        "batter_hand": batter_hand,
        "pitcher_hand": pitcher_hand,
        "batter_avg_vs_hand": _avg(split_rows),
        "batter_k_rate_vs_hand": _k_rate(split_rows),
        "batter_recent_hits_vs_lhp": sum(to_float(first_value(row, ["hits", "h"])) for row in lhp_rows) if lhp_rows else "",
        "batter_recent_hits_vs_rhp": sum(to_float(first_value(row, ["hits", "h"])) for row in rhp_rows) if rhp_rows else "",
        "pitcher_avg_allowed_vs_hand": pitcher_avg_allowed.get((normalized_pitcher, batter_hand), ""),
        "source": str(source),
        "sourceUpdatedAt": _source_updated_at(source),
        "generatedAt": generated_at,
        "pregameSafe": True,
        "labelsExcluded": True,
        "warnings": "",
        "seedSource": seed.get("seedSource", ""),
        "seedMarketCount": seed.get("seedMarketCount", ""),
        "seedRowCount": seed.get("seedRowCount", ""),
        "seedSubjectNameSource": seed.get("seedSubjectNameSource", ""),
        "enrichmentStatus": "; ".join(enrichment_status) or "partial",
    }


def _latest_pitcher_hand_by_name(rows: list[dict[str, str]]) -> dict[str, str]:
    hands: dict[str, str] = {}
    for row in rows:
        pitcher = normalize_player_name(first_value(row, ["player", "playerName", "pitcher", "name"]))
        hand = _normalized_hand(first_value(row, ["throws", "p_throws", "pitcher_hand"]))
        if pitcher and hand:
            hands[pitcher] = hand
    return hands


def _pitcher_avg_allowed_by_name(rows: list[dict[str, str]]) -> dict[tuple[str, str], float | str]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        pitcher = normalize_player_name(first_value(row, ["player", "playerName", "pitcher", "name"]))
        hand = _normalized_hand(first_value(row, ["batter_hand", "stand"]))
        if pitcher and hand:
            grouped[(pitcher, hand)].append(row)
    return {group_key: _avg(group_rows) for group_key, group_rows in grouped.items()}


def _avg(rows: list[dict[str, str]]) -> float | str:
    at_bats = sum(to_float(first_value(row, ["atBats", "at_bats", "battersFaced", "bf"])) for row in rows)
    hits = sum(to_float(first_value(row, ["hits", "h"])) for row in rows)
    if at_bats <= 0:
        return ""
    return round(hits / at_bats, 6)


def _k_rate(rows: list[dict[str, str]]) -> float | str:
    pa = sum(to_float(first_value(row, ["plateAppearances", "pa", "battersFaced", "bf"])) for row in rows)
    strikeouts = sum(to_float(first_value(row, ["strikeOuts", "strikeouts", "k"])) for row in rows)
    if pa <= 0:
        return ""
    return round(strikeouts / pa, 6)


def _normalized_hand(value: Any) -> str:
    text = clean(value).upper()
    if text in {"L", "LEFT", "LHP"}:
        return "L"
    if text in {"R", "RIGHT", "RHP"}:
        return "R"
    if text in {"S", "B", "SWITCH"}:
        return "S"
    return ""


def _has_any_column(rows: list[dict[str, str]], aliases: list[str]) -> bool:
    return any(any(clean(row.get(alias)) for alias in aliases) for row in rows)


def _source_updated_at(path: Path) -> str:
    try:
        return date.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""


def _read_date_rows(path: Path, date_label: str, date_aliases: tuple[str, ...] = ("date", "game_date", "gameDate", "event_date")) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_date = clean(first_value(row, list(date_aliases)))
            if raw_date[:10] == date_label:
                rows.append(dict(row))
    return rows


def _has_any_split_stat(row: dict[str, Any]) -> bool:
    for field in (
        "batter_avg_vs_hand",
        "batter_k_rate_vs_hand",
        "batter_recent_hits_vs_lhp",
        "batter_recent_hits_vs_rhp",
        "pitcher_avg_allowed_vs_hand",
    ):
        if clean(row.get(field)):
            return True
    return False


def _context_key(row: dict[str, Any], date_label: str, season: int) -> str:
    return "|".join(
        [
            date_label,
            str(season),
            clean(row.get("normalizedPlayer")) or normalize_player_name(row.get("player")),
            clean(row.get("normalizedTeam")) or normalize_team(row.get("team")),
            clean(row.get("normalizedOpponent")) or normalize_opponent(row.get("opponent")),
        ]
    )


def _sample(row: dict[str, Any]) -> dict[str, str]:
    return {
        "player": clean(row.get("player")),
        "team": clean(row.get("team")),
        "opponent": clean(row.get("opponent")),
        "normalizedPlayer": clean(row.get("normalizedPlayer")),
        "normalizedTeam": clean(row.get("normalizedTeam")),
        "normalizedOpponent": clean(row.get("normalizedOpponent")),
    }
