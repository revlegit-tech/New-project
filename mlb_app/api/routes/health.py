from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from mlb_app.api.dependencies import get_container
from mlb_app.api.models import HealthResponse
from mlb_app.container import AppContainer

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse, name="native_health_live")
async def live() -> dict[str, Any]:
    return {"status": "ok", "ok": True, "checks": {"process": "alive"}}


@router.get("/ready", response_model=HealthResponse, name="native_health_ready")
async def ready(container: Annotated[AppContainer, Depends(get_container)]) -> dict[str, Any]:
    def _checks() -> dict[str, Any]:
        migrations = container.db.migration_versions()
        metrics = container.metrics.snapshot()
        return {
            "database": {
                "ok": True,
                "path": str(container.db.path),
                "migrations": migrations,
                "migrationCount": len(migrations),
            },
            "services": {
                "appStatus": container.app_status_service is not None,
                "edgeBoard": container.edge_board_service is not None,
                "picks": container.picks_service is not None,
                "modelRegistry": container.model_registry_service is not None,
                "predictionAudit": container.prediction_audit_service is not None,
            },
            "observability": {
                "metrics": {
                    "counterSeries": len(metrics.get("counters", [])),
                    "histogramSeries": len(metrics.get("histograms", [])),
                }
            },
        }

    checks = await asyncio.to_thread(_checks)
    return {"status": "ok", "ok": True, "checks": checks}
