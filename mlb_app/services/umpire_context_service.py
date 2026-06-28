from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.data_source_capability_service import resolve_date_mode
from mlb_app.services.runtime_status_service import safe_relpath


NEUTRAL_K_BOOST = "0"
NEUTRAL_RUN_ENVIRONMENT = "1"


class UmpireContextService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def context_for_game(
        self,
        *,
        date_label: str | None,
        season: int | None,
        game_pk: str = "",
        home_team: str = "",
        away_team: str = "",
    ) -> dict[str, Any]:
        target_date, _mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        for path in self._candidate_paths(target_date, selected_season):
            for row in _read_csv(path):
                if not _matches(row, game_pk=game_pk, home_team=home_team, away_team=away_team):
                    continue
                return self._payload(
                    date_label=target_date,
                    season=selected_season,
                    row=row,
                    source=safe_relpath(path, self.settings.root_dir),
                    flags=[],
                )
        return self.neutral_fallback(date_label=target_date, season=selected_season, game_pk=game_pk, home_team=home_team, away_team=away_team)

    def status(self, *, date_label: str | None, season: int | None) -> dict[str, Any]:
        target_date, _mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        files = [path for path in self._candidate_paths(target_date, selected_season) if path.is_file()]
        rows = sum(len(_read_csv(path)) for path in files)
        return {
            "status": "available" if rows > 0 else "neutral_fallback",
            "available": rows > 0,
            "rows": rows,
            "fileCount": len(files),
            "paths": [safe_relpath(path, self.settings.root_dir) for path in files[-5:]],
            "criticalForBoard": False,
        }

    def neutral_fallback(self, *, date_label: str, season: int, game_pk: str = "", home_team: str = "", away_team: str = "") -> dict[str, Any]:
        return self._payload(
            date_label=date_label,
            season=season,
            row={"game_pk": game_pk, "home_team": home_team, "away_team": away_team},
            source="neutral_fallback",
            flags=["neutral_fallback"],
        )

    def _candidate_paths(self, date_label: str, season: int) -> list[Path]:
        return [
            self.settings.data_dir / "warehouse" / "umpires" / f"umpires_{date_label}.csv",
            self.settings.data_dir / "warehouse" / "umpires" / f"umpire_assignments_{date_label}.csv",
            self.settings.data_dir / "cache" / "umpires" / f"umpires_{season}.csv",
            self.settings.data_dir / f"umpires_{season}.csv",
        ]

    def _payload(self, *, date_label: str, season: int, row: dict[str, Any], source: str, flags: list[str]) -> dict[str, Any]:
        quality_flags = _flags(row.get("quality_flags"), flags)
        assignment_status = _clean(row.get("assignment_status")) or ("neutral_fallback" if "neutral_fallback" in quality_flags else "available")
        return {
            "date": _clean(row.get("date")) or date_label,
            "season": int(row.get("season") or season),
            "game_pk": _clean(row.get("game_pk") or row.get("gamePk")),
            "home_team": _clean(row.get("home_team") or row.get("homeTeam")),
            "away_team": _clean(row.get("away_team") or row.get("awayTeam")),
            "umpire_name": _clean(row.get("umpire_name") or row.get("umpire") or row.get("home_plate_umpire") or row.get("name")) or "Unknown",
            "assignment_status": assignment_status,
            "k_boost": _clean(row.get("k_boost") or row.get("umpire_k_boost")) or NEUTRAL_K_BOOST,
            "run_environment": _clean(row.get("run_environment") or row.get("umpire_run_environment")) or NEUTRAL_RUN_ENVIRONMENT,
            "zone_tendency": _clean(row.get("zone_tendency")) or "neutral",
            "source": source,
            "source_snapshot_at": _clean(row.get("source_snapshot_at") or row.get("snapshot_at")) or datetime.now(timezone.utc).isoformat(),
            "quality_flags": quality_flags,
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _matches(row: dict[str, Any], *, game_pk: str, home_team: str, away_team: str) -> bool:
    if game_pk and _clean(row.get("game_pk") or row.get("gamePk")) == str(game_pk):
        return True
    if home_team and away_team:
        return _key(row.get("home_team") or row.get("homeTeam")) == _key(home_team) and _key(row.get("away_team") or row.get("awayTeam")) == _key(away_team)
    return not game_pk and not home_team and not away_team


def _flags(existing: Any, extra: list[str]) -> list[str]:
    flags = [part.strip() for part in str(existing or "").split(",") if part.strip()]
    for flag in extra:
        if flag not in flags:
            flags.append(flag)
    return flags


def _key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _clean(value: Any) -> str:
    return str(value or "").strip()
