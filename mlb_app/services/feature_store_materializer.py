from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.feature_store_schema import postgame_label_names, pregame_feature_names
from mlb_app.services.data_source_capability_service import DataSourceCapabilityService, resolve_date_mode
from mlb_app.services.game_market_context_service import GameMarketContextService
from mlb_app.services.playerboard_builder import (
    DEFAULT_MARKETS,
    aggregate_book_prices,
    american_implied_percent,
    normalize_prop_row,
)
from mlb_app.services.runtime_status_service import safe_relpath

SCHEMA_VERSION = "feature-store-materializer.v1"


class FeatureStoreMaterializer:
    """Build a local, pregame-safe prop feature matrix from cached artifacts."""

    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.capabilities = DataSourceCapabilityService(settings)
        self.game_markets = GameMarketContextService(settings)

    def feature_path(self, date_label: str) -> Path:
        return self.settings.data_dir / "features" / f"prop_features_{date_label}.csv"

    def status(
        self,
        *,
        date_label: str | None = None,
        season: int | None = None,
        materialize: bool = False,
        limit: int = 5000,
    ) -> dict[str, Any]:
        target_date, mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        path = self.feature_path(target_date)
        warnings: list[str] = []
        if materialize or not path.is_file():
            result = self.materialize(date_label=target_date, season=selected_season, limit=limit)
            warnings.extend(result.get("warnings") or [])
        rows = _count_csv_rows(path)
        missing_groups = list(self.capabilities.audit_feature_availability(target_date, selected_season).get("missingFeatureGroups") or [])
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok" if path.is_file() else "partial",
            "date": target_date,
            "season": selected_season,
            "resolvedDateMode": mode,
            "rows": rows,
            "path": safe_relpath(path, self.settings.root_dir),
            "pregameSafe": True,
            "labelsExcluded": self._labels_excluded(path),
            "missingFeatureGroups": missing_groups,
            "warnings": warnings if warnings else ([] if path.is_file() else ["Feature matrix has not been materialized yet."]),
            "externalApiCallsMade": False,
            "modelTrainingTriggered": False,
        }

    def materialize(self, *, date_label: str, season: int, limit: int = 5000) -> dict[str, Any]:
        path = self.feature_path(date_label)
        rows = self._feature_rows(date_label=date_label, season=season, limit=limit)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = pregame_feature_names()
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows([{field: row.get(field, "") for field in fieldnames} for row in rows])
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok",
            "date": date_label,
            "season": season,
            "rows": len(rows),
            "path": safe_relpath(path, self.settings.root_dir),
            "pregameSafe": True,
            "labelsExcluded": True,
            "missingFeatureGroups": list(self.capabilities.audit_feature_availability(date_label, season).get("missingFeatureGroups") or []),
            "warnings": [] if rows else ["No cached prop candidates were available for feature materialization."],
            "externalApiCallsMade": False,
            "modelTrainingTriggered": False,
        }

    def _feature_rows(self, *, date_label: str, season: int, limit: int) -> list[dict[str, Any]]:
        capability = self.capabilities.audit_feature_availability(date_label, season)
        missing_groups = list(capability.get("missingFeatureGroups") or [])
        snapshot_at = self._source_snapshot_at(date_label)
        rows: list[dict[str, Any]] = []
        for prop in self._prop_candidates(date_label, limit=limit):
            context = self.game_markets.context_by_team(date_label=date_label, team=str(prop.get("team") or ""), opponent=str(prop.get("opponent") or ""))
            rows.append(self._row_from_prop(prop, date_label=date_label, season=season, missing_groups=missing_groups, snapshot_at=snapshot_at, context=context))
        return rows[: max(0, int(limit or 0))]

    def _prop_candidates(self, date_label: str, *, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in self._prop_paths(date_label):
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    for raw in csv.DictReader(handle):
                        prop = normalize_prop_row(dict(raw), date_label)
                        if prop.get("player") and prop.get("market") in set(DEFAULT_MARKETS):
                            prop["rawSource"] = safe_relpath(path, self.settings.root_dir)
                            rows.append(prop)
            except Exception:
                continue
        return aggregate_book_prices(rows)[:limit]

    def _prop_paths(self, date_label: str) -> list[Path]:
        paths = [
            self.settings.data_dir / "odds" / f"propline_props_{date_label}.csv",
            self.settings.data_dir / "playerboard" / f"playerboard_{self.settings.current_season}.csv",
        ]
        return [path for path in paths if path.is_file()]

    def _row_from_prop(
        self,
        prop: dict[str, Any],
        *,
        date_label: str,
        season: int,
        missing_groups: list[str],
        snapshot_at: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        game_total = context.get("gameTotal") if isinstance(context.get("gameTotal"), dict) else {}
        moneyline = context.get("moneyline") if isinstance(context.get("moneyline"), dict) else {}
        return {
            "date": date_label,
            "season": season,
            "game_pk": prop.get("gamePk") or prop.get("game_pk") or "",
            "player_id": prop.get("playerId") or prop.get("player_id") or "",
            "player": prop.get("player") or "",
            "team": prop.get("team") or "",
            "opponent": prop.get("opponent") or "",
            "market": prop.get("market") or "",
            "side": prop.get("rawLabel") or "Over",
            "line": prop.get("line") or "",
            "book": prop.get("book") or "",
            "american_odds": prop.get("americanOdds") or "",
            "implied_probability_percent": _round(american_implied_percent(prop.get("americanOdds")), 4) if prop.get("americanOdds") else "",
            "book_count": prop.get("bookCount") or len(prop.get("books") or []),
            "consensus_open_total": "",
            "consensus_current_total": game_total.get("line") or "",
            "team_no_vig_win_prob_current": moneyline.get("implied_probability") or "",
            "moneyline_movement": "",
            "park_factor_runs": prop.get("park_factor") or prop.get("parkFactor") or "",
            "probable_pitcher_hand": prop.get("probablePitcherHand") or prop.get("pitcherHand") or "",
            "weather_temperature_f": prop.get("weather_temperature_f") or prop.get("weatherTemperatureF") or "",
            "weather_wind_mph": prop.get("weather_wind_mph") or prop.get("weatherWindMph") or "",
            "weather_wind_direction": prop.get("weather_wind_direction") or prop.get("weatherWindDirection") or "",
            "weather_humidity": prop.get("weather_humidity") or prop.get("weatherHumidity") or "",
            "batter_xba": prop.get("batter_xba") or "",
            "batter_xslg": prop.get("batter_xslg") or "",
            "batter_barrel_rate": prop.get("batter_barrel_rate") or "",
            "batter_hard_hit_rate": prop.get("batter_hard_hit_rate") or "",
            "pitcher_xwoba_allowed": prop.get("pitcher_xwoba_allowed") or "",
            "pitcher_whiff_rate": prop.get("pitcher_whiff_rate") or "",
            "pitcher_csw_rate": prop.get("pitcher_csw_rate") or "",
            "pitcher_barrel_rate_allowed": prop.get("pitcher_barrel_rate_allowed") or "",
            "umpire_name": prop.get("umpire_name") or "",
            "umpire_k_boost": prop.get("umpire_k_boost") or "",
            "umpire_run_environment": prop.get("umpire_run_environment") or "",
            "hit_rate_5": prop.get("hit_rate_5") or "",
            "hit_rate_10": prop.get("hit_rate_10") or "",
            "hit_rate_20": prop.get("hit_rate_20") or "",
            "source_snapshot_at": snapshot_at,
            "source_freshness_minutes": _freshness_minutes(snapshot_at),
            "missing_feature_groups": json.dumps(missing_groups, ensure_ascii=True),
        }

    def _source_snapshot_at(self, date_label: str) -> str:
        files = self._prop_paths(date_label)
        latest = max(files, key=lambda path: path.stat().st_mtime, default=None)
        if latest is None:
            return ""
        return datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat()

    def _labels_excluded(self, path: Path) -> bool:
        if not path.is_file():
            return True
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
        except Exception:
            return False
        blocked = set(postgame_label_names())
        return not any(name in blocked for name in header)


def _count_csv_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except Exception:
        return 0


def _freshness_minutes(snapshot_at: str) -> str:
    if not snapshot_at:
        return ""
    try:
        timestamp = datetime.fromisoformat(snapshot_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return str(round(max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds() / 60.0), 3))


def _round(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")
