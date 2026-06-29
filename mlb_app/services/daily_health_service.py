from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.collector_verification_service import CollectorVerificationService, resolve_date_mode
from mlb_app.services.feature_store_materializer import FeatureStoreMaterializer
from mlb_app.services.model_training_readiness_service import ModelTrainingReadinessService

SCHEMA_VERSION = "daily-health.v1"
WORKFLOW_STATUS_MAP = {
    "success": "ok",
    "ok": "ok",
    "warning": "warning",
    "failed": "failed",
    "error": "failed",
    "cancelled": "failed",
    "missing": "unknown",
}


class DailyHealthService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def payload(self, *, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        selected_date, _mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)

        collector = CollectorVerificationService(settings=self.settings).payload(
            date_label=selected_date,
            season=selected_season,
        )
        feature_store = FeatureStoreMaterializer(self.settings).status(
            date_label=selected_date,
            season=selected_season,
            materialize=False,
        )
        readiness = ModelTrainingReadinessService(self.settings).payload(
            date_label=selected_date,
            season=selected_season,
        )
        scheduled_collector = _workflow_status(self.settings.data_dir / "status" / "daily_workflow_status.json")
        weekly_repair = _workflow_status(self.settings.data_dir / "health" / "latest_weekly_repair.json")

        board_available = int(collector.get("counts", {}).get("activePlayerboardRows") or 0) > 0
        feature_available = Path(str(feature_store.get("path") or "")).is_file() or int(feature_store.get("rows") or 0) > 0
        readiness_available = readiness.get("status") in {"ok", "warning"} or bool(readiness.get("markets"))
        production_ready = bool(readiness.get("readyForProductionTraining")) and bool(readiness.get("eligibleProductionMarkets"))

        warnings = list(feature_store.get("warnings") or []) + list(readiness.get("warnings") or [])
        recommendations = list(collector.get("recommendations") or [])
        if scheduled_collector in {"failed", "unknown"}:
            recommendations.append("Scheduled collector needs attention, but existing board snapshot can still serve if available.")
        if weekly_repair in {"failed", "unknown"}:
            recommendations.append("Weekly repair has no passing latest summary; keep repair in safe mode until logs are reviewed.")

        serving_safe = board_available
        overall = "ok"
        if not serving_safe:
            overall = "failed"
        elif collector.get("status") not in {"ok", "partial"} or scheduled_collector in {"failed", "unknown"} or weekly_repair in {"failed", "unknown"}:
            overall = "warning"

        return {
            "schemaVersion": SCHEMA_VERSION,
            "date": selected_date,
            "season": selected_season,
            "overallStatus": overall,
            "servingSafe": serving_safe,
            "boardAvailable": board_available,
            "featureStoreAvailable": feature_available,
            "modelReadinessAvailable": readiness_available,
            "productionTrainingReady": production_ready,
            "scheduledCollectorStatus": scheduled_collector,
            "weeklyRepairStatus": weekly_repair,
            "stages": _stages(collector, feature_store, readiness, scheduled_collector, weekly_repair),
            "warnings": warnings,
            "recommendations": recommendations,
            "modelTrainingTriggered": False,
            "externalApiCallsMade": False,
        }


def _workflow_status(path: Path) -> str:
    if not path.exists():
        return "unknown"
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return "failed"
    raw = str(payload.get("status") or ("ok" if payload.get("ok") is True else "failed")).lower()
    return WORKFLOW_STATUS_MAP.get(raw, "warning")


def _stage(name: str, status: str, *, rows: int = 0, files: list[str] | None = None, warnings: list[str] | None = None, recommendations: list[str] | None = None, recoverable: bool = True) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat()
    return {
        "name": name,
        "status": status,
        "startedAt": now,
        "finishedAt": now,
        "durationMs": 0,
        "rows": rows,
        "files": files or [],
        "warnings": warnings or [],
        "recommendations": recommendations or [],
        "artifacts": [],
        "errorType": "" if status != "failed" else "missing_required_artifact",
        "recoverable": recoverable,
    }


def _stages(
    collector: dict[str, Any],
    feature_store: dict[str, Any],
    readiness: dict[str, Any],
    scheduled_collector: str,
    weekly_repair: str,
) -> list[dict[str, Any]]:
    counts = collector.get("counts") if isinstance(collector.get("counts"), dict) else {}
    return [
        _stage("props collection", "ok" if counts.get("propsRows") else "warning", rows=int(counts.get("propsRows") or 0)),
        _stage("odds snapshots", "ok" if counts.get("oddsSnapshots") else "warning", rows=int(counts.get("oddsSnapshots") or 0)),
        _stage("normalized odds", "ok" if counts.get("normalizedOddsFiles") else "warning", rows=int(counts.get("normalizedOddsFiles") or 0)),
        _stage("game markets", "ok" if counts.get("gameMarketRows") else "warning", rows=int(counts.get("gameMarketRows") or 0)),
        _stage("weather", "warning", recommendations=["Weather context is optional and uses fallback when unavailable."]),
        _stage("Savant/history", "warning", recommendations=["Savant/history repair is bounded by scheduled safe mode."]),
        _stage("umpire context", "ok" if counts.get("umpireRows") else "warning", rows=int(counts.get("umpireRows") or 0)),
        _stage("playerboard build", "ok" if counts.get("activePlayerboardRows") else "failed", rows=int(counts.get("activePlayerboardRows") or 0), recoverable=False),
        _stage("feature store", "ok" if feature_store.get("rows") else "warning", rows=int(feature_store.get("rows") or 0), warnings=list(feature_store.get("warnings") or [])),
        _stage("model readiness", str(readiness.get("status") or "warning"), recommendations=list(readiness.get("warnings") or [])),
        _stage("calibration/backtest status", "warning" if not readiness.get("readyForProductionTraining") else "ok"),
        _stage("report/summary", "ok"),
        _stage("scheduled collector", scheduled_collector),
        _stage("weekly repair", weekly_repair),
    ]
