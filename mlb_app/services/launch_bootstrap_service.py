from __future__ import annotations

from datetime import date as date_type, datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.actionnetwork_snapshot_status_service import ActionNetworkSnapshotWorkflow
from mlb_app.services.data_freshness_service import file_age_seconds
from mlb_app.services.runtime_lock import runtime_lock
from mlb_app.services.runtime_status_service import safe_relpath, sanitize_public, write_status_json


class LaunchBootstrapService:
    def __init__(
        self,
        settings: Settings,
        *,
        snapshot_workflow: ActionNetworkSnapshotWorkflow | None = None,
        stale_lock_seconds: int = 900,
        freshness_seconds: int = 1800,
    ) -> None:
        self.settings = settings
        self.snapshot_workflow = snapshot_workflow or ActionNetworkSnapshotWorkflow(settings)
        self.stale_lock_seconds = stale_lock_seconds
        self.freshness_seconds = freshness_seconds
        self.status_path = settings.data_dir / "status" / "launch_bootstrap_status.json"
        self.runtime_status_path = settings.data_dir / "status" / "runtime_status.json"
        self.lock_path = settings.data_dir / "status" / "launch_bootstrap.lock"

    def run(self, *, date_text: str | None = None, skip: bool = False, today: date_type | None = None) -> dict[str, Any]:
        today = today or date_type.today()
        date_text = _normalize_date(date_text, today=today)
        if skip:
            payload = self._payload("skipped", date_text, steps=[{"name": "bootstrap", "status": "skipped"}])
            write_status_json(self.status_path, payload)
            self._write_runtime_status("success")
            return payload

        with runtime_lock(self.lock_path, stale_after_seconds=self.stale_lock_seconds) as lock:
            if not lock.acquired:
                payload = self._payload("skipped", date_text, warnings=[lock.warning], lock=lock.status)
                write_status_json(self.status_path, payload)
                return payload

            warnings = [lock.warning] if lock.warning else []
            steps: list[dict[str, Any]] = []
            snapshot_path = self.settings.data_dir / "warehouse" / "normalized" / "odds" / f"actionnetwork_all_markets_{date_text}.csv"
            age = file_age_seconds(snapshot_path)
            if age is not None and age <= self.freshness_seconds:
                steps.append({"name": "actionnetwork_live_snapshot", "status": "skipped", "reason": "fresh", "ageSeconds": age})
            elif date_text == today.isoformat():
                result = self.snapshot_workflow.run(date_text=date_text, retries=1)
                steps.append({"name": "actionnetwork_live_snapshot", "status": result["status"], "outputs": result.get("outputs", {})})
                warnings.extend(result.get("warnings", []))
            else:
                steps.append({"name": "actionnetwork_live_snapshot", "status": "skipped", "reason": "launch bootstrap is forward-only"})

            playerboard_path = self.settings.data_dir / "playerboard" / f"playerboard_{self.settings.current_season}.csv"
            if playerboard_path.exists():
                steps.append({"name": "playerboard", "status": "skipped", "reason": "existing snapshot available", "file": safe_relpath(playerboard_path, self.settings.root_dir)})
            else:
                steps.append({"name": "playerboard", "status": "skipped", "reason": "required inputs unavailable for lightweight launch build"})

            status = "warning" if any(step["status"] == "warning" for step in steps) or warnings else "success"
            payload = self._payload(status, date_text, steps=steps, warnings=warnings)
            write_status_json(self.status_path, payload)
            self._write_runtime_status(status)
            return payload

    def _write_runtime_status(self, status: str) -> None:
        write_status_json(
            self.runtime_status_path,
            {
                "schemaVersion": "runtime-status-file.v1",
                "status": status,
                "ok": status in {"success", "warning"},
                "entrypoint": "mlb_app.asgi:app",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _payload(self, status: str, date_text: str, **extra: Any) -> dict[str, Any]:
        return sanitize_public(
            {
                "schemaVersion": "launch-bootstrap.v1",
                "status": status,
                "ok": status in {"success", "warning", "skipped"},
                "date": date_text,
                "finishedAt": datetime.now(timezone.utc).isoformat(),
                **extra,
            }
        )


def _normalize_date(value: str | None, *, today: date_type) -> str:
    if not value or value == "today":
        return today.isoformat()
    return value
