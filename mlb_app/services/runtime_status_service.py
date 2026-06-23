from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings

STATUS_SCHEMA = "runtime-status.v1"
SENSITIVE_KEY_RE = re.compile(r"(secret|token|key|password|database_url|dsn)", re.IGNORECASE)
ABSOLUTE_PATH_RE = re.compile(r"([A-Za-z]:\\Users\\[^\\\s\"]+|/mnt/data[^\s\"]*)")


def safe_relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.name


def sanitize_public(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_RE.search(key_text):
                cleaned[key_text] = "[redacted]"
            else:
                cleaned[key_text] = sanitize_public(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_public(item) for item in value]
    if isinstance(value, str):
        return ABSOLUTE_PATH_RE.sub("[redacted-path]", value)
    return value


def write_status_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = sanitize_public(payload)
    path.write_text(json.dumps(safe_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_status_json(path: Path, *, root: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing",
            "ok": False,
            "file": safe_relpath(path, root),
            "warnings": ["Status file is missing."],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {
            "status": "degraded",
            "ok": False,
            "file": safe_relpath(path, root),
            "warnings": [f"Could not read status file: {type(error).__name__}"],
        }
    if not isinstance(payload, dict):
        return {
            "status": "degraded",
            "ok": False,
            "file": safe_relpath(path, root),
            "warnings": ["Status file did not contain a JSON object."],
        }
    payload.setdefault("file", safe_relpath(path, root))
    return sanitize_public(payload)


class RuntimeStatusService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.status_dir = settings.data_dir / "status"

    def health(self) -> dict[str, Any]:
        return {
            "schemaVersion": "runtime-health.v1",
            "status": "ok",
            "ok": True,
            "service": "mlb_app",
            "entrypoint": "mlb_app.asgi:app",
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }

    def runtime_status(self) -> dict[str, Any]:
        launch = read_status_json(self.status_dir / "launch_bootstrap_status.json", root=self.settings.root_dir)
        runtime = read_status_json(self.status_dir / "runtime_status.json", root=self.settings.root_dir)
        statuses = [str(launch.get("status", "missing")), str(runtime.get("status", "missing"))]
        overall = "ok" if any(status == "success" for status in statuses) else "degraded"
        return sanitize_public(
            {
                "schemaVersion": STATUS_SCHEMA,
                "status": overall,
                "ok": overall == "ok",
                "checkedAt": datetime.now(timezone.utc).isoformat(),
                "runtime": runtime,
                "launchBootstrap": launch,
                "environment": {
                    "dbEnabled": os.environ.get("DB_ENABLED", ""),
                    "dbFallbackToCsv": os.environ.get("DB_FALLBACK_TO_CSV", ""),
                    "gameMarketEnrichmentEnabled": os.environ.get("GAME_MARKET_ENRICHMENT_ENABLED", ""),
                    "teamGameMarketProjectionsEnabled": os.environ.get("TEAM_GAME_MARKET_PROJECTIONS_ENABLED", ""),
                },
            }
        )

    def workflow_status(self) -> dict[str, Any]:
        snapshot = read_status_json(self.status_dir / "actionnetwork_live_snapshot_status.json", root=self.settings.root_dir)
        daily = read_status_json(self.status_dir / "daily_workflow_status.json", root=self.settings.root_dir)
        statuses = [str(snapshot.get("status", "missing")), str(daily.get("status", "missing"))]
        failed = any(status == "failed" for status in statuses)
        warning = any(status in {"warning", "degraded", "missing"} for status in statuses)
        overall = "failed" if failed else "warning" if warning else "success"
        return sanitize_public(
            {
                "schemaVersion": "workflow-status.v1",
                "status": overall,
                "ok": overall in {"success", "warning"},
                "checkedAt": datetime.now(timezone.utc).isoformat(),
                "actionnetworkLiveSnapshot": snapshot,
                "dailyWorkflow": daily,
            }
        )
