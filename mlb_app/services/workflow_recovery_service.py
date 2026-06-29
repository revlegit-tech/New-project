from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FRESH_STATUSES = {"ok", "success", "warning", "skipped"}
FAILED_STATUSES = {"failed", "missing", "error"}


@dataclass(frozen=True)
class WorkflowStagePlan:
    name: str
    status: str
    action: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "action": self.action, "reason": self.reason}


class WorkflowRecoveryService:
    def __init__(self, *, temp_roots: list[Path] | None = None) -> None:
        self.temp_roots = temp_roots or []

    def plan(self, stages: list[dict[str, Any]], *, force: bool = False) -> list[dict[str, str]]:
        planned: list[dict[str, str]] = []
        for stage in stages:
            name = str(stage.get("name") or "")
            status = str(stage.get("status") or "missing").lower()
            fresh = bool(stage.get("fresh", status in FRESH_STATUSES))
            if force:
                item = WorkflowStagePlan(name=name, status=status, action="rerun", reason="force requested")
            elif fresh and status in FRESH_STATUSES:
                item = WorkflowStagePlan(name=name, status=status, action="skip", reason="fresh completed stage")
            elif status in FAILED_STATUSES or not fresh:
                item = WorkflowStagePlan(name=name, status=status, action="rerun", reason="failed, missing, or stale stage")
            else:
                item = WorkflowStagePlan(name=name, status=status, action="skip", reason="stage is recoverable without rerun")
            planned.append(item.as_dict())
        return planned

    def clear_stale_temp_files(self) -> dict[str, Any]:
        removed: list[str] = []
        warnings: list[str] = []
        for root in self.temp_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or not _is_temp_file(path):
                    continue
                try:
                    path.unlink()
                    removed.append(str(path))
                except OSError as error:
                    warnings.append(f"Could not remove {path.name}: {error}")
        return {
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "removed": removed,
            "warnings": warnings,
        }


def _is_temp_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".tmp") or ".tmp." in name or name.startswith(".tmp")
