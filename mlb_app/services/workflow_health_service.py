from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings


class WorkflowHealthService:
    def __init__(self, settings: Settings = default_settings, *, data_dir: Path | None = None) -> None:
        self.settings = settings
        self.data_dir = data_dir or settings.data_dir

    def payload(self) -> dict[str, Any]:
        health_dir = self.data_dir / "health"
        summary_files = {
            "dailyHealth": health_dir / "latest_daily_health.json",
            "dailyGrading": health_dir / "latest_grading_summary.json",
            "weeklyRepair": health_dir / "latest_weekly_repair.json",
        }
        summaries: dict[str, Any] = {}
        warnings: list[str] = []
        errors: list[str] = []
        for key, path in summary_files.items():
            item = self._read_summary(key, path)
            summaries[key] = item
            warnings.extend(f"{key}: {warning}" for warning in item.get("warnings", []))
            errors.extend(f"{key}: {error}" for error in item.get("errors", []))
            if item.get("exists") and not item.get("ok"):
                errors.append(f"{key}: latest summary is not OK.")
        return {
            "ok": not errors,
            "healthDir": str(health_dir),
            "summaries": summaries,
            "warnings": warnings,
            "errors": errors,
        }

    @staticmethod
    def _read_summary(key: str, path: Path) -> dict[str, Any]:
        item: dict[str, Any] = {
            "key": key,
            "exists": path.exists(),
            "file": str(path),
            "size": path.stat().st_size if path.exists() else 0,
            "ok": False,
            "date": "",
            "checkedAt": "",
            "warnings": [],
            "errors": [],
        }
        if not path.exists():
            item["warnings"].append(f"{path.name} does not exist yet.")
            return item
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as error:  # noqa: BLE001 - safe health boundary
            item["errors"].append(f"could not read {path.name}: {error}")
            return item
        item["ok"] = bool(payload.get("ok", True))
        item["date"] = str(payload.get("date", ""))
        item["checkedAt"] = str(payload.get("checkedAt", payload.get("checked_at", "")))
        item["warnings"] = list(payload.get("warnings") or [])
        item["errors"] = list(payload.get("errors") or [])
        return item
