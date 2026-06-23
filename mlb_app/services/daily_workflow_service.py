from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mlb_app.config import Settings
from mlb_app.services.actionnetwork_snapshot_status_service import ActionNetworkSnapshotWorkflow, default_command_runner
from mlb_app.services.mlb_truth_log_resolver import load_truth_logs
from mlb_app.services.runtime_lock import runtime_lock
from mlb_app.services.runtime_status_service import safe_relpath, sanitize_public, write_status_json

StepRunner = Callable[[str, list[str]], subprocess.CompletedProcess[str]]


def default_step_runner(_name: str, command: list[str]) -> subprocess.CompletedProcess[str]:
    return default_command_runner(command)


class DailyWorkflowService:
    def __init__(
        self,
        settings: Settings,
        *,
        snapshot_workflow: ActionNetworkSnapshotWorkflow | None = None,
        step_runner: StepRunner = default_step_runner,
        stale_lock_seconds: int = 3600,
    ) -> None:
        self.settings = settings
        self.snapshot_workflow = snapshot_workflow or ActionNetworkSnapshotWorkflow(settings)
        self.step_runner = step_runner
        self.lock_path = settings.data_dir / "status" / "daily_workflow.lock"
        self.status_path = settings.data_dir / "status" / "daily_workflow_status.json"
        self.stale_lock_seconds = stale_lock_seconds

    def run(self, *, date_text: str, season: int | None = None) -> dict[str, Any]:
        season = season or self.settings.current_season
        with runtime_lock(self.lock_path, stale_after_seconds=self.stale_lock_seconds) as lock:
            if not lock.acquired:
                payload = self._payload("skipped", date_text, season, steps=[], warnings=[lock.warning], lock=lock.status)
                write_status_json(self.status_path, payload)
                return payload

            warnings = [lock.warning] if lock.warning else []
            steps: list[dict[str, Any]] = []
            snapshot = self.snapshot_workflow.run(date_text=date_text, retries=1)
            steps.append({"name": "collect_actionnetwork_live_snapshot", "status": snapshot["status"], "outputs": snapshot.get("outputs", {})})
            warnings.extend(snapshot.get("warnings", []))

            steps.append({"name": "collect_propline_oddspapi", "status": "skipped", "reason": "not configured for scheduler wrapper"})
            steps.append(self._existing_or_skipped("build_playerboard", self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv"))
            steps.append(self._existing_or_skipped("build_edge_board", self.settings.data_dir / "edge_board" / f"edge_board_{date_text}.json"))
            truth = self._load_truth_logs(season)
            truth_available = bool(truth.source_dir) and truth.covers(date_text)
            steps.append(
                {
                    "name": "update_mlb_truth_logs",
                    "status": "skipped" if not truth_available else "success",
                    "reason": "truth logs unavailable for date" if not truth_available else "truth logs available",
                }
            )
            steps.append(self._script_step("build_actionnetwork_event_bridge", "scripts/build_actionnetwork_event_bridge.py", date_text, season, required_inputs=truth_available))
            bridge_path = self.settings.data_dir / "warehouse" / "quality" / f"actionnetwork_event_game_bridge_{date_text}.csv"
            steps.append(self._script_step("validate_actionnetwork_labels", "scripts/validate_actionnetwork_odds.py", date_text, season, extra=["--bridge-path", str(bridge_path)], required_inputs=truth_available and bridge_path.exists()))
            steps.append(self._script_step("build_odds_movement_features", "scripts/build_actionnetwork_odds_movement_features.py", date_text, season))
            features_path = self.settings.data_dir / "warehouse" / "features" / f"actionnetwork_odds_movement_features_{date_text}.csv"
            labels_path = self.settings.data_dir / "warehouse" / "ml_labels" / f"actionnetwork_prop_labels_{season}.csv"
            steps.append(
                self._script_step(
                    "build_event_confirmed_training_dataset",
                    "scripts/build_actionnetwork_training_dataset.py",
                    date_text,
                    season,
                    required_inputs=features_path.exists() and labels_path.exists(),
                )
            )
            registry_exists = self.settings.model_registry_path.exists()
            playerboard_path = self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv"
            if registry_exists and playerboard_path.exists():
                result = self.step_runner(
                    "score_shadow_models",
                    [
                        sys.executable,
                        str(self.settings.root_dir / "scripts" / "score_playerboard_shadow.py"),
                        "--input",
                        str(playerboard_path),
                    ],
                )
                steps.append({"name": "score_shadow_models", "status": "success" if result.returncode == 0 else "failed", "returncode": result.returncode})
            else:
                steps.append({"name": "score_shadow_models", "status": "skipped", "reason": "missing registry/models or playerboard"})

            status = _overall_status(steps)
            payload = self._payload(status, date_text, season, steps=steps, warnings=warnings)
            write_status_json(self.status_path, payload)
            return payload

    def _existing_or_skipped(self, name: str, path: Path) -> dict[str, Any]:
        if path.exists():
            return {"name": name, "status": "success", "reason": "existing generated artifact available", "file": safe_relpath(path, self.settings.root_dir)}
        return {"name": name, "status": "skipped", "reason": "artifact missing; generation is outside lightweight scheduler scaffold"}

    def _load_truth_logs(self, season: int):
        for candidate in (
            self.settings.data_dir / "cloud" / "season_logs",
            self.settings.data_dir / "warehouse" / "season_logs",
            self.settings.data_dir / "cache" / "incremental_stats",
        ):
            truth = load_truth_logs(str(season), truth_dir=candidate)
            if truth.source_dir:
                return truth
        return load_truth_logs(str(season), truth_dir=self.settings.data_dir / "cloud" / "season_logs")

    def _script_step(
        self,
        name: str,
        script: str,
        date_text: str,
        season: int,
        *,
        extra: list[str] | None = None,
        required_inputs: bool = True,
    ) -> dict[str, Any]:
        if not required_inputs:
            return {"name": name, "status": "skipped", "reason": "required inputs unavailable"}
        command = [sys.executable, str(self.settings.root_dir / script), "--date", date_text]
        if name not in {"build_odds_movement_features"}:
            command.extend(["--season", str(season)])
        if extra:
            command.extend(extra)
        result = self.step_runner(name, command)
        return {
            "name": name,
            "status": "success" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
        }

    def _payload(self, status: str, date_text: str, season: int, **extra: Any) -> dict[str, Any]:
        return sanitize_public(
            {
                "schemaVersion": "daily-workflow.v1",
                "status": status,
                "ok": status in {"success", "warning", "skipped"},
                "date": date_text,
                "season": season,
                "finishedAt": datetime.now(timezone.utc).isoformat(),
                **extra,
            }
        )


def _overall_status(steps: list[dict[str, Any]]) -> str:
    statuses = [str(step.get("status", "")) for step in steps]
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "success"
