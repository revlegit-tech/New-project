from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult
from mlb_app.services.context_sources.bullpen_context_provider import BullpenContextProvider
from mlb_app.services.context_sources.game_market_context_provider import GameMarketContextProvider
from mlb_app.services.context_sources.handedness_platoon_context_provider import (
    HAND_PLATOON_FIELDS,
    HandednessPlatoonContextProvider,
)
from mlb_app.services.context_sources.mlb_stats_context_provider import MLBStatsContextProvider
from mlb_app.services.context_sources.mlb_stats_context_provider import PITCHER_CONTEXT_FIELDS, PLAYER_RECENT_FORM_FIELDS
from mlb_app.services.context_sources.odds_movement_context_provider import OddsMovementContextProvider
from mlb_app.services.context_sources.savant_statcast_context_provider import STATCAST_FIELDS, SavantStatcastContextProvider
from mlb_app.services.context_sources.umpire_context_provider import UmpireContextProvider
from mlb_app.services.context_sources.weather_context_provider import WeatherContextProvider


AUDIT_FIELD_CONTRACTS = {
    "player_recent_form": PLAYER_RECENT_FORM_FIELDS,
    "pitcher_context": PITCHER_CONTEXT_FIELDS,
    "statcast": STATCAST_FIELDS,
    "handedness_platoon": HAND_PLATOON_FIELDS,
}


class FeatureSourceAuditService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> dict[str, Any]:
        stats = MLBStatsContextProvider(self.settings)
        results = {
            "player_recent_form": stats.player_recent_form(date_label=date_label, season=season),
            "pitcher_context": stats.pitcher_context(date_label=date_label, season=season),
            "odds_movement": OddsMovementContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "game_markets": GameMarketContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "weather": WeatherContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "statcast": SavantStatcastContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "handedness_platoon": HandednessPlatoonContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "bullpen_context": BullpenContextProvider(self.settings).materialize(date_label=date_label, season=season),
            "umpire": UmpireContextProvider(self.settings).materialize(date_label=date_label, season=season),
        }
        payload = self._summary(date_label=date_label, season=season, results=results)
        path = self.settings.data_dir / "context" / f"context_source_audit_{date_label}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["path"] = str(path)
        return payload

    def _summary(self, *, date_label: str, season: int, results: dict[str, ContextProviderResult]) -> dict[str, Any]:
        providers = {name: result.to_dict() for name, result in results.items()}
        for name, expected_fields in AUDIT_FIELD_CONTRACTS.items():
            if name in providers:
                field_status = _field_status(results[name], expected_fields)
                providers[name]["readyFields"] = field_status["readyFields"]
                providers[name]["missingFields"] = field_status["missingFields"]
                if name == "handedness_platoon":
                    diagnostics = providers[name].get("diagnostics") or {}
                    providers[name]["rowsWithBatterHand"] = diagnostics.get("contextRowsWithBatterHand", 0)
                    providers[name]["rowsWithPitcherHand"] = diagnostics.get("contextRowsWithPitcherHand", 0)
                    providers[name]["rowsWithSplitStats"] = diagnostics.get("contextRowsWithSplitStats", 0)
                    providers[name]["externalApiCallsMade"] = diagnostics.get("externalApiCallsMade", providers[name].get("externalApiCallsMade", 0))
                    providers[name]["pregameSafe"] = diagnostics.get("pregameSafe", providers[name].get("pregameSafe", True))
                    providers[name]["labelsExcluded"] = diagnostics.get("labelsExcluded", providers[name].get("labelsExcluded", True))
                if name in {"player_recent_form", "pitcher_context"}:
                    diagnostics = providers[name].get("diagnostics") or {}
                    providers[name]["rowsGenerated"] = diagnostics.get("rowsGenerated", providers[name].get("rows", 0))
                    providers[name]["rowsGeneratedFromBoard"] = diagnostics.get("rowsGeneratedFromBoard", 0)
                    providers[name]["historicalRowsUsed"] = diagnostics.get("historicalRowsUsed", 0)
                    providers[name]["externalApiCallsMade"] = diagnostics.get("externalApiCallsMade", providers[name].get("externalApiCallsMade", 0))
                    providers[name]["pregameSafe"] = diagnostics.get("pregameSafe", providers[name].get("pregameSafe", True))
                    providers[name]["labelsExcluded"] = diagnostics.get("labelsExcluded", providers[name].get("labelsExcluded", True))
        ready = sorted(name for name, result in results.items() if result.status == "ok" and result.rows > 0)
        fallback = sorted(name for name, result in results.items() if result.status == "neutral_fallback")
        partial = sorted(name for name, result in results.items() if result.status == "partial")
        missing = sorted(name for name, result in results.items() if result.status in {"missing", "error"})
        warnings = [warning for result in results.values() for warning in result.warnings]
        coverage = {name: _coverage_for_result(name, result) for name, result in results.items()}
        return {
            "date": date_label,
            "season": int(season),
            "providers": providers,
            "providerStatuses": {name: result.status for name, result in results.items()},
            "rowsByProvider": {name: result.rows for name, result in results.items()},
            "contextCoverageByGroup": coverage,
            "contextFeatureGroups": {
                "ready": sorted(name for name in ready if name not in fallback),
                "partial": partial,
                "fallback": fallback,
                "missing": sorted(name for name, result in results.items() if result.status in {"missing", "error"}),
            },
            "missingFeatureGroups": missing,
            "readyFeatureGroups": ready,
            "warnings": warnings,
            "externalApiCallsMade": sum(result.externalApiCallsMade for result in results.values()),
            "pregameSafe": all(result.pregameSafe for result in results.values()),
            "labelsExcluded": all(result.labelsExcluded for result in results.values()),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }


def _field_status(result: ContextProviderResult, expected_fields: list[str]) -> dict[str, list[str]]:
    fields: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        with open(result.path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = [field for field in (reader.fieldnames or []) if field]
            rows = [dict(row) for row in reader]
    except OSError:
        fields = []
    ready = [field for field in expected_fields if field in fields and any(_populated(row.get(field)) for row in rows)]
    missing = [field for field in expected_fields if field not in ready]
    return {"readyFields": ready, "missingFields": missing}


def _coverage_for_result(name: str, result: ContextProviderResult) -> dict[str, Any]:
    fields: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        with open(result.path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = [field for field in (reader.fieldnames or []) if field]
            rows = [dict(row) for row in reader]
    except OSError:
        rows = []
    fallback_rows = sum(1 for row in rows if "fallback" in str(row.get("source") or row.get("assignment_status") or row.get("warnings") or "").lower())
    populated_rows = sum(1 for row in rows if any(_populated(value) for field, value in row.items() if field not in _META_FIELDS))
    missing_feature_fields = [
        field
        for field in _feature_fields_for_group(name, fields)
        if field in fields and not any(_populated(row.get(field)) for row in rows)
    ]
    missing_required = [
        field
        for field in _required_fields_for_group(name, fields)
        if field not in fields or not any(_populated(row.get(field)) for row in rows)
    ]
    total = int(result.rows)
    populated_percent = round((populated_rows / total) * 100.0, 2) if total else 0.0
    status = "fallback" if result.status == "neutral_fallback" else result.status
    return {
        "rows": total,
        "populatedRows": populated_rows,
        "fallbackRows": fallback_rows if result.status == "neutral_fallback" else int(result.diagnostics.get("fallbackRows") or fallback_rows),
        "rejectedRows": _rejected_rows(result),
        "missingRequiredFields": missing_required,
        "missingFeatureFields": missing_feature_fields,
        "populatedPercent": populated_percent,
        "source": result.source,
        "status": status,
        "warnings": list(result.warnings),
        "sampleRows": rows[:3] if result.status in {"ok", "partial"} else [],
        "sampleJoinedRows": rows[:3] if result.status in {"ok", "partial"} else [],
        "sampleFallbackRows": rows[:3] if result.status == "neutral_fallback" else [],
        "sampleRejectedRows": list(result.diagnostics.get("sampleRejectedRows") or [])[:3],
        "sampleRejectedIdentityRows": list(result.diagnostics.get("sampleRejectedRows") or [])[:3],
    }


_META_FIELDS = {
    "date",
    "season",
    "source",
    "generatedAt",
    "sourceUpdatedAt",
    "pregameSafe",
    "labelsExcluded",
    "warnings",
}


def _required_fields_for_group(name: str, fields: list[str]) -> list[str]:
    contracts = {
        "weather": ["date", "season", "team", "opponent", "pregameSafe", "labelsExcluded"],
        "game_markets": ["date", "season", "team", "opponent", "market", "source"],
        "bullpen_context": ["date", "season", "team", "opponent", "pregameSafe", "labelsExcluded"],
        "statcast": ["date", "season", "player", "team", "pregameSafe", "labelsExcluded"],
        "umpire": ["date", "season", "assignment_status", "pregameSafe", "labelsExcluded"],
    }
    return [field for field in contracts.get(name, []) if field in fields or name in contracts]


def _feature_fields_for_group(name: str, fields: list[str]) -> list[str]:
    contracts = {
        "game_markets": ["moneyline", "total", "team_total", "run_line", "american_odds", "implied_probability"],
        "statcast": [
            "barrel_rate",
            "hard_hit_rate",
            "xwoba",
            "xba",
            "xslg",
            "batter_babip",
            "batter_k_rate",
            "batter_walk_rate",
            "batter_ld_rate",
            "batter_gb_rate",
            "batter_sprint_speed",
        ],
    }
    return [field for field in contracts.get(name, []) if field in fields]


def _rejected_rows(result: ContextProviderResult) -> int:
    diagnostics = result.diagnostics or {}
    explicit = diagnostics.get("rejectedRows")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            return 0
    total = 0
    for key, value in diagnostics.items():
        if key.startswith("rowsRejected"):
            try:
                total += int(value or 0)
            except (TypeError, ValueError):
                continue
    return total


def _populated(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and text.lower() not in {"nan", "none", "null"})
