from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings

GRADING_STATES = {
    "not_started",
    "waiting_for_finals",
    "boxscores_loaded",
    "grading_running",
    "graded",
    "partial",
    "failed",
}


@dataclass(frozen=True)
class GradingState:
    state: str
    ok: bool
    date: str = ""
    latest_fully_graded_date: str = ""
    checked_at: str = ""
    file: str = ""
    exists: bool = False
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    summary: dict[str, int] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "ok": self.ok,
            "date": self.date,
            "latestFullyGradedDate": self.latest_fully_graded_date,
            "checkedAt": self.checked_at,
            "file": self.file,
            "exists": self.exists,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "summary": self.summary or {},
        }


class GradingStateService:
    """Reads the daily grading summary and exposes bettor-friendly state.

    This service deliberately separates today's board date from the latest fully
    graded slate. That prevents ungraded rows from being mistaken for completed
    win-rate or ROI history.
    """

    def __init__(self, settings: Settings = default_settings, *, data_dir: Path | None = None) -> None:
        self.settings = settings
        self.data_dir = data_dir or settings.data_dir

    @property
    def latest_summary_path(self) -> Path:
        return self.data_dir / "health" / "latest_grading_summary.json"

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        requested_date = str((query.get("date") or [""])[0] or "")
        state = self.read_state(requested_date=requested_date)
        payload = state.as_dict()
        payload["requestedDate"] = requested_date
        return payload

    def read_state(self, *, requested_date: str = "") -> GradingState:
        path = self.latest_summary_path
        if not path.exists():
            return GradingState(
                state="not_started",
                ok=False,
                file=str(path),
                exists=False,
                warnings=("No grading summary exists yet. Run Daily playerboard grading after final boxscores.",),
                checked_at=datetime.now(timezone.utc).isoformat(),
                summary={
                    "backtestRowsForDate": 0,
                    "gradedBacktestRowsForDate": 0,
                    "mlRowsForDate": 0,
                    "gradedMlRowsForDate": 0,
                },
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as error:  # noqa: BLE001 - safe boundary for health endpoint
            return GradingState(
                state="failed",
                ok=False,
                file=str(path),
                exists=True,
                checked_at=datetime.now(timezone.utc).isoformat(),
                errors=(f"Could not read grading summary: {error}",),
            )

        counts = raw.get("counts") or {}
        warnings = list(raw.get("warnings") or [])
        errors = list(raw.get("errors") or [])
        date = str(raw.get("date") or "")
        checked_at = str(raw.get("checkedAt") or raw.get("checked_at") or "")

        summary = {
            "backtestRowsForDate": int(counts.get("backtestRowsForDate") or 0),
            "gradedBacktestRowsForDate": int(counts.get("gradedBacktestRowsForDate") or 0),
            "mlRowsForDate": int(counts.get("mlRowsForDate") or 0),
            "gradedMlRowsForDate": int(counts.get("gradedMlRowsForDate") or 0),
        }

        if requested_date and date and requested_date != date:
            warnings.append(f"Latest grading summary is for {date}, not requested date {requested_date}.")

        state = self._infer_state(raw, summary, warnings, errors, requested_date=requested_date, summary_date=date)
        latest_fully_graded = date if state == "graded" else str(raw.get("latestFullyGradedDate") or raw.get("latest_fully_graded_date") or "")
        ok = state not in {"failed", "not_started"} and not errors

        return GradingState(
            state=state,
            ok=ok,
            date=date,
            latest_fully_graded_date=latest_fully_graded,
            checked_at=checked_at,
            file=str(path),
            exists=True,
            warnings=tuple(warnings),
            errors=tuple(errors),
            summary=summary,
        )

    @staticmethod
    def _infer_state(
        raw: dict[str, Any],
        summary: dict[str, int],
        warnings: list[str],
        errors: list[str],
        *,
        requested_date: str,
        summary_date: str,
    ) -> str:
        explicit = str(raw.get("state") or raw.get("status") or "").strip().lower()
        if explicit in GRADING_STATES:
            return explicit
        if errors or raw.get("ok") is False:
            return "failed"
        if requested_date and summary_date and requested_date != summary_date:
            return "partial"

        backtest_rows = summary["backtestRowsForDate"]
        graded_backtest = summary["gradedBacktestRowsForDate"]
        ml_rows = summary["mlRowsForDate"]
        graded_ml = summary["gradedMlRowsForDate"]
        total_rows = backtest_rows + ml_rows
        total_graded = graded_backtest + graded_ml

        if total_rows <= 0:
            return "waiting_for_finals"
        if total_graded <= 0:
            return "waiting_for_finals"
        if total_graded < total_rows:
            return "partial"
        if warnings:
            return "partial"
        return "graded"
