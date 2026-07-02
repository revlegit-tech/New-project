from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import (
    ContextProviderResult,
    clean,
    context_path,
    first_value,
    read_csv_rows,
    schedule_side_rows,
    write_csv_rows,
)
from mlb_app.services.game_market_context_service import CANONICAL_GAME_MARKET_FIELDS, NORMALIZED_GAME_MARKET_FIELDS


GAME_MARKET_CONTEXT_FIELDS = [
    "date",
    "season",
    "event_id",
    "game_id",
    "source",
    "source_event_id",
    "source_market_key",
    "book",
    "home_team",
    "away_team",
    "team",
    "opponent",
    "market",
    "side",
    "line",
    "american_odds",
    "implied_probability",
    "total",
    "team_total",
    "moneyline",
    "run_line",
    "last_update",
    "snapshot_at",
    "is_live",
    "raw_source",
    "generatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
]

_GAME_MARKET_KEYS = {
    "h2h": "moneyline",
    "moneyline": "moneyline",
    "money_line": "moneyline",
    "spread": "run_line",
    "spreads": "run_line",
    "run_line": "run_line",
    "runline": "run_line",
    "total": "game_total",
    "totals": "game_total",
    "game_total": "game_total",
    "team_total": "team_total",
    "team_totals": "team_total",
}


class GameMarketContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "game_markets", f"game_markets_{date_label}.csv")
        warnings: list[str] = []
        generated_at = datetime.now(timezone.utc).isoformat()
        source_path = self.settings.data_dir / "warehouse" / "normalized" / "game_markets" / f"game_markets_{date_label}.csv"
        if source_path.is_file():
            rows = [_context_row(row, date_label=date_label, season=season, generated_at=generated_at, raw_source=str(source_path)) for row in read_csv_rows(source_path)]
            write_csv_rows(output_path, rows, GAME_MARKET_CONTEXT_FIELDS)
            return _result("ok" if rows else "missing", date_label, season, len(rows), output_path, warnings, diagnostics={"sourcePath": str(source_path)})

        warnings.append("Normalized game market artifact not found.")
        odds_path, odds_rows = self._latest_actionnetwork_odds(date_label)
        if odds_path:
            game_rows = [
                _context_row(row, date_label=date_label, season=season, generated_at=generated_at, raw_source=str(odds_path))
                for row in odds_rows
                if _is_true_game_market_row(row)
            ]
            if game_rows:
                warnings.append(f"Game market context materialized from local ActionNetwork normalized odds: {odds_path}")
                write_csv_rows(output_path, game_rows, GAME_MARKET_CONTEXT_FIELDS)
                status = "partial" if any(str(row.get("is_live")).lower() == "true" for row in game_rows) else "ok"
                return _result(status, date_label, season, len(game_rows), output_path, warnings, diagnostics={"sourcePath": str(odds_path), "playerPropRowsIgnored": len(odds_rows) - len(game_rows)})
            warnings.append(f"ActionNetwork normalized odds contained no true game-market rows; player-prop odds ignored: {odds_path}")

        schedule_rows, schedule_source = schedule_side_rows(self.settings, date_label)
        if schedule_rows:
            fallback_warning = "slate fallback only: no true local game-market odds available; odds fields left null"
            rows = [
                {
                    "date": date_label,
                    "season": season,
                    "event_id": row.get("game_pk", ""),
                    "game_id": row.get("game_pk", ""),
                    "source": f"neutral_fallback_from_slate:{schedule_source}" if schedule_source else "neutral_fallback_from_slate",
                    "source_event_id": row.get("game_pk", ""),
                    "source_market_key": "",
                    "book": "",
                    "home_team": row.get("home_team", ""),
                    "away_team": row.get("away_team", ""),
                    "team": row.get("team", ""),
                    "opponent": row.get("opponent", ""),
                    "market": "slate",
                    "side": "",
                    "line": "",
                    "american_odds": "",
                    "implied_probability": "",
                    "total": "",
                    "team_total": "",
                    "moneyline": "",
                    "run_line": "",
                    "last_update": "",
                    "snapshot_at": "",
                    "is_live": "",
                    "raw_source": schedule_source,
                    "generatedAt": generated_at,
                    "pregameSafe": True,
                    "labelsExcluded": True,
                    "warnings": fallback_warning,
                }
                for row in schedule_rows
            ]
            warnings.append(fallback_warning)
            write_csv_rows(output_path, rows, GAME_MARKET_CONTEXT_FIELDS)
            return _result(
                "neutral_fallback",
                date_label,
                season,
                len(rows),
                output_path,
                warnings,
                critical=False,
                diagnostics={"fallbackRows": len(rows), "scheduleSource": schedule_source},
            )

        write_csv_rows(output_path, [], GAME_MARKET_CONTEXT_FIELDS)
        return _result("missing", date_label, season, 0, output_path, warnings)

    def _latest_actionnetwork_odds(self, date_label: str) -> tuple[Path | None, list[dict[str, str]]]:
        root = self.settings.data_dir / "warehouse" / "normalized" / "odds"
        candidates = [
            root / f"actionnetwork_all_markets_{date_label}.csv",
            *sorted(root.glob(f"actionnetwork_all_markets_{date_label}_*.csv"), key=lambda item: item.stat().st_mtime, reverse=True),
        ]
        for path in candidates:
            rows = read_csv_rows(path)
            if rows:
                return path, rows
        return None, []


def _result(
    status: str,
    date_label: str,
    season: int,
    rows: int,
    path: Path,
    warnings: list[str],
    *,
    critical: bool = True,
    diagnostics: dict[str, Any] | None = None,
) -> ContextProviderResult:
    return ContextProviderResult(
        status=status,
        date=date_label,
        season=season,
        source="game_markets",
        rows=rows,
        path=str(path),
        warnings=warnings,
        criticalForBoard=critical,
        diagnostics=diagnostics or {},
    )


def _context_row(row: dict[str, Any], *, date_label: str, season: int, generated_at: str, raw_source: str) -> dict[str, Any]:
    market = clean(first_value(row, ["market", "market_type", "market_key", "market_slug"]))
    canonical = _GAME_MARKET_KEYS.get(market.lower(), market)
    line = clean(first_value(row, ["line", "current_total", "current_run_line", "team_total"]))
    american_odds = first_value(row, ["american_odds", "americanOdds"], "")
    moneyline = first_value(row, ["current_moneyline", "moneyline"], "") or (american_odds if canonical == "moneyline" else "")
    total = first_value(row, ["current_total", "total"], "") or (line if canonical == "game_total" else "")
    team_total = first_value(row, ["team_total"], "") or (line if canonical == "team_total" else "")
    run_line = first_value(row, ["current_run_line", "run_line"], "") or (line if canonical == "run_line" else "")
    return {
        "date": clean(first_value(row, ["date", "game_date"], date_label))[:10] or date_label,
        "season": clean(first_value(row, ["season"], season)) or season,
        "event_id": first_value(row, ["event_id", "game_id", "game_pk"], ""),
        "game_id": first_value(row, ["game_id", "event_id", "game_pk"], ""),
        "source": first_value(row, ["source"], "game_markets"),
        "source_event_id": first_value(row, ["source_event_id", "event_id", "game_id", "game_pk"], ""),
        "source_market_key": first_value(row, ["source_market_key", "market_slug", "market_type", "market"], ""),
        "book": first_value(row, ["book", "book_display_name", "bookKey"], ""),
        "home_team": first_value(row, ["home_team", "homeTeam"], ""),
        "away_team": first_value(row, ["away_team", "awayTeam"], ""),
        "team": first_value(row, ["team"], ""),
        "opponent": first_value(row, ["opponent"], ""),
        "market": canonical,
        "side": first_value(row, ["side", "bet_side", "option_type"], ""),
        "line": line,
        "american_odds": american_odds,
        "implied_probability": first_value(row, ["implied_probability"], ""),
        "total": total if canonical == "game_total" or total else "",
        "team_total": team_total if canonical == "team_total" or team_total else "",
        "moneyline": moneyline if canonical == "moneyline" or moneyline else "",
        "run_line": run_line if canonical == "run_line" or run_line else "",
        "last_update": first_value(row, ["last_update", "lastUpdate"], ""),
        "snapshot_at": first_value(row, ["snapshot_at", "source_snapshot_at", "snapshot_time"], ""),
        "is_live": first_value(row, ["is_live"], ""),
        "raw_source": first_value(row, ["raw_source"], raw_source),
        "generatedAt": generated_at,
        "pregameSafe": str(first_value(row, ["is_live"], "")).lower() != "true",
        "labelsExcluded": True,
        "warnings": "live row marked not pregame safe" if str(first_value(row, ["is_live"], "")).lower() == "true" else "",
    }


def _is_true_game_market_row(row: dict[str, Any]) -> bool:
    if clean(first_value(row, ["player", "player_name", "player_id"])):
        return False
    market_values = [
        clean(first_value(row, ["market"])).lower(),
        clean(first_value(row, ["market_type"])).lower(),
        clean(first_value(row, ["market_slug"])).lower(),
        clean(first_value(row, ["market_group"])).lower(),
    ]
    return any(value in _GAME_MARKET_KEYS for value in market_values)
