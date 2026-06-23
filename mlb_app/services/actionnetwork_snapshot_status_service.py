from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mlb_app.config import Settings
from mlb_app.services.runtime_lock import runtime_lock
from mlb_app.services.runtime_status_service import safe_relpath, sanitize_public, write_status_json

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def default_command_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def parse_key_value_output(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class ActionNetworkSnapshotWorkflow:
    def __init__(
        self,
        settings: Settings,
        *,
        command_runner: CommandRunner = default_command_runner,
        stale_lock_seconds: int = 1800,
        sleep_seconds: float = 2.0,
    ) -> None:
        self.settings = settings
        self.command_runner = command_runner
        self.stale_lock_seconds = stale_lock_seconds
        self.sleep_seconds = sleep_seconds
        self.status_path = settings.data_dir / "status" / "actionnetwork_live_snapshot_status.json"
        self.lock_path = settings.data_dir / "status" / "actionnetwork_live_snapshot.lock"

    def run(self, *, date_text: str, market: str = "all", refresh: bool = False, retries: int = 1) -> dict[str, Any]:
        with runtime_lock(self.lock_path, stale_after_seconds=self.stale_lock_seconds) as lock:
            if not lock.acquired:
                payload = self._payload("skipped", date_text, warnings=[lock.warning], lock=lock.status)
                write_status_json(self.status_path, payload)
                return payload

            warnings = [lock.warning] if lock.warning else []
            command = [
                sys.executable,
                str(self.settings.root_dir / "scripts" / "collect_actionnetwork_odds.py"),
                "--date",
                date_text,
                "--market",
                market,
            ]
            if refresh:
                command.append("--refresh")

            attempts: list[dict[str, Any]] = []
            result: subprocess.CompletedProcess[str] | None = None
            for attempt in range(1, retries + 2):
                result = self.command_runner(command)
                attempts.append({"attempt": attempt, "returncode": result.returncode})
                if result.returncode == 0:
                    break
                if attempt <= retries and self.sleep_seconds:
                    time.sleep(self.sleep_seconds)

            assert result is not None
            parsed = parse_key_value_output((result.stdout or "") + "\n" + (result.stderr or ""))
            status = "success" if result.returncode == 0 else "warning"
            if result.returncode != 0:
                warnings.append("ActionNetwork live snapshot collection failed; downstream workflow can continue degraded.")
            outputs = {
                key: safe_relpath(Path(value), self.settings.root_dir)
                for key, value in parsed.items()
                if key in {"saved_csv", "saved_snapshot_csv", "snapshot_raw_dir"}
            }
            payload = self._payload(status, date_text, warnings=warnings, outputs=outputs, attempts=attempts)
            write_status_json(self.status_path, payload)
            return payload

    def _payload(self, status: str, date_text: str, **extra: Any) -> dict[str, Any]:
        return sanitize_public(
            {
                "schemaVersion": "actionnetwork-live-snapshot.v1",
                "status": status,
                "ok": status in {"success", "warning", "skipped"},
                "date": date_text,
                "finishedAt": datetime.now(timezone.utc).isoformat(),
                **extra,
            }
        )
