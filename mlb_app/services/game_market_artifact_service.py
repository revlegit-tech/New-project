from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.game_market_context_service import CANONICAL_GAME_MARKET_FIELDS, CANONICAL_GAME_MARKETS, write_normalized_game_markets
from mlb_app.services.runtime_status_service import safe_relpath


class GameMarketArtifactService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def artifact_path(self, date_label: str) -> Path:
        return self.settings.data_dir / "warehouse" / "normalized" / "game_markets" / f"game_markets_{date_label}.csv"

    def status(self, *, date_label: str) -> dict[str, Any]:
        path = self.artifact_path(date_label)
        rows = _count_rows(path)
        return {
            "status": "available" if path.is_file() and rows > 0 else "missing",
            "available": path.is_file() and rows > 0,
            "exists": path.is_file(),
            "rows": rows,
            "path": safe_relpath(path, self.settings.root_dir),
        }

    def build_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        date_label: str,
        season: int,
        source: str = "fixture",
        output_path: Path | None = None,
        snapshot_at: str | None = None,
    ) -> dict[str, Any]:
        snapshot = snapshot_at or datetime.now(timezone.utc).isoformat()
        canonical = canonical_game_market_rows(rows, date_label=date_label, season=season, source=source, snapshot_at=snapshot)
        path = output_path or self.artifact_path(date_label)
        write_normalized_game_markets(path, canonical)
        return {
            "schemaVersion": "game-market-artifact.v1",
            "status": "ok" if canonical else "missing",
            "date": date_label,
            "season": season,
            "rows": len(canonical),
            "path": safe_relpath(path, self.settings.root_dir),
            "externalApiCallsMade": False,
            "modelTrainingTriggered": False,
        }


def canonical_game_market_rows(
    rows: list[dict[str, Any]],
    *,
    date_label: str,
    season: int,
    source: str,
    snapshot_at: str,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        market_type = _market_type(raw)
        if not market_type:
            continue
        game_id = _clean(raw.get("game_id") or raw.get("game_pk") or raw.get("event_id") or raw.get("source_event_id"))
        team = _clean(raw.get("team"))
        if market_type in {"game_total", "alt_game_total"}:
            team = _clean(raw.get("home_team"))
        buckets[(game_id, team, market_type)].append(raw)

    canonical: list[dict[str, Any]] = []
    for (_game_id, _team, market_type), bucket in sorted(buckets.items()):
        first = bucket[0]
        team = _team_for_bucket(first, market_type)
        opponent = _opponent_for_bucket(first, team)
        current_values = [_float(row.get("current_moneyline") or row.get("american_odds") or row.get("price") or row.get("odds")) for row in bucket]
        current_values = [value for value in current_values if value is not None]
        lines = [_float(row.get("line") or row.get("current_total") or row.get("current_run_line") or row.get("team_total")) for row in bucket]
        lines = [value for value in lines if value is not None]
        current_line = _avg(lines)
        row = {field: "" for field in CANONICAL_GAME_MARKET_FIELDS}
        row.update(
            {
                "date": _clean(first.get("date")) or date_label,
                "season": int(first.get("season") or season),
                "game_id": _clean(first.get("game_id") or first.get("event_id") or first.get("source_event_id") or first.get("game_pk")),
                "game_pk": _clean(first.get("game_pk") or first.get("game_id") or first.get("event_id") or first.get("source_event_id")),
                "home_team": _clean(first.get("home_team")),
                "away_team": _clean(first.get("away_team")),
                "team": team,
                "opponent": opponent,
                "market_type": market_type,
                "source": _clean(first.get("source")) or source,
                "source_snapshot_at": _clean(first.get("source_snapshot_at") or first.get("snapshot_at")) or snapshot_at,
                "quality_flags": _quality_flags(bucket, market_type),
            }
        )
        if market_type == "moneyline":
            current_moneyline = _avg(current_values)
            row["open_moneyline"] = _clean(first.get("open_moneyline")) or _format_number(current_moneyline)
            row["current_moneyline"] = _format_number(current_moneyline)
            row["no_vig_win_prob_open"] = _format_probability(_implied_probability(current_moneyline))
            row["no_vig_win_prob_current"] = _format_probability(_implied_probability(current_moneyline))
            row["book_count_moneyline"] = len(bucket)
        elif market_type in {"game_total", "alt_game_total"}:
            row["open_total"] = _clean(first.get("open_total")) or _format_number(current_line)
            row["current_total"] = _format_number(current_line)
            row["book_count_total"] = len(bucket)
        elif market_type in {"run_line", "alt_run_line"}:
            row["open_run_line"] = _clean(first.get("open_run_line")) or _format_number(current_line)
            row["current_run_line"] = _format_number(current_line)
            row["book_count_runline"] = len(bucket)
        elif market_type == "team_total":
            row["team_total"] = _format_number(current_line)
            row["book_count_total"] = len(bucket)
        canonical.append(row)
    return canonical


def _market_type(row: dict[str, Any]) -> str:
    raw = _clean(row.get("market_type") or row.get("market") or row.get("source_market_key")).lower()
    return CANONICAL_GAME_MARKETS.get(raw, raw if raw in set(CANONICAL_GAME_MARKETS.values()) else "")


def _team_for_bucket(row: dict[str, Any], market_type: str) -> str:
    if market_type in {"game_total", "alt_game_total"}:
        return ""
    team = _clean(row.get("team"))
    if team:
        return team
    side = _clean(row.get("side") or row.get("name"))
    if side.lower() in {"home", _clean(row.get("home_team")).lower()}:
        return _clean(row.get("home_team"))
    if side.lower() in {"away", _clean(row.get("away_team")).lower()}:
        return _clean(row.get("away_team"))
    return side if side.lower() not in {"over", "under"} else ""


def _opponent_for_bucket(row: dict[str, Any], team: str) -> str:
    if _clean(row.get("opponent")):
        return _clean(row.get("opponent"))
    if not team:
        return ""
    home = _clean(row.get("home_team"))
    away = _clean(row.get("away_team"))
    return away if _key(team) == _key(home) else home if _key(team) == _key(away) else ""


def _quality_flags(rows: list[dict[str, Any]], market_type: str) -> str:
    flags = []
    if not rows:
        flags.append("missing")
    if market_type == "team_total":
        flags.append("team_total_available")
    if len(rows) == 1:
        flags.append("single_book")
    return ",".join(flags)


def _count_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        import csv

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except Exception:
        return 0


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _float(value: Any) -> float | None:
    try:
        parsed = float(str(value).replace("+", "").strip())
    except Exception:
        return None
    return parsed if math.isfinite(parsed) else None


def _implied_probability(odds: float | None) -> float | None:
    if odds is None or odds == 0:
        return None
    return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _format_probability(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _clean(value: Any) -> str:
    return str(value or "").strip()
