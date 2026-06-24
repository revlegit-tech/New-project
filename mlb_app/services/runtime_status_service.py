from __future__ import annotations

import json
import os
import re
import sys
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


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _database_url_kind(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unset"
    if text.startswith("sqlite:///"):
        return "sqlite_file"
    if text.startswith("sqlite://"):
        return "sqlite"
    if "postgres" in text:
        return "postgres"
    return "configured"


def _live_runtime_payload(settings: Settings) -> dict[str, Any]:
    root = settings.root_dir.resolve()
    prefix = Path(sys.prefix).resolve()
    base_prefix = Path(getattr(sys, "base_prefix", sys.prefix)).resolve()
    executable_name = Path(sys.executable).name
    pythonpath = os.environ.get("PYTHONPATH", "")
    pythonpath_parts = [part for part in pythonpath.split(os.pathsep) if part]
    pythonpath_includes_root = any(
        Path(part).resolve() == root
        for part in pythonpath_parts
        if part
    )

    is_project_venv = _is_relative_to(prefix, root) and prefix.name.lower() == ".venv"
    cwd_matches_root = Path.cwd().resolve() == root

    warnings: list[str] = []
    if not is_project_venv:
        warnings.append("Runtime is not using the project .venv prefix.")
    if not pythonpath_includes_root:
        warnings.append("PYTHONPATH does not include the project root.")
    if not cwd_matches_root:
        warnings.append("Process working directory does not match the project root.")

    return {
        "schemaVersion": "runtime-live.v1",
        "entrypoint": "mlb_app.asgi:app",
        "python": {
            "version": sys.version.split()[0],
            "implementation": sys.implementation.name,
            "executableName": executable_name,
            "prefixKind": "project_venv" if is_project_venv else "external",
            "prefixLabel": ".venv" if is_project_venv else "external",
            "isProjectVenv": is_project_venv,
            "basePrefixOutsideProject": not _is_relative_to(base_prefix, root),
        },
        "process": {
            "cwdMatchesRoot": cwd_matches_root,
            "pythonPathIncludesRoot": pythonpath_includes_root,
        },
        "environment": {
            "dbEnabled": os.environ.get("DB_ENABLED", ""),
            "dbFallbackToCsv": os.environ.get("DB_FALLBACK_TO_CSV", ""),
            "gameMarketEnrichmentEnabled": os.environ.get("GAME_MARKET_ENRICHMENT_ENABLED", ""),
            "teamGameMarketProjectionsEnabled": os.environ.get("TEAM_GAME_MARKET_PROJECTIONS_ENABLED", ""),
            "databaseUrlKind": _database_url_kind(os.environ.get("DATABASE_URL", "")),
            "databaseUrlConfigured": bool(os.environ.get("DATABASE_URL", "")),
        },
        "warnings": warnings,
    }


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
        live_runtime = _live_runtime_payload(self.settings)
        statuses = [str(launch.get("status", "missing")), str(runtime.get("status", "missing"))]
        overall = "ok" if any(status == "success" for status in statuses) else "degraded"
        return sanitize_public(
            {
                "schemaVersion": STATUS_SCHEMA,
                "status": overall,
                "ok": overall == "ok",
                "checkedAt": datetime.now(timezone.utc).isoformat(),
                "runtime": runtime,
                "liveRuntime": live_runtime,
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
