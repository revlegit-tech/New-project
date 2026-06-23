from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.runtime_status_service import read_status_json, safe_relpath, sanitize_public


class ActionNetworkHealthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def snapshot_health(self, *, date_text: str | None = None) -> dict[str, Any]:
        date_text = _date_text(date_text)
        status = read_status_json(
            self.settings.data_dir / "status" / "actionnetwork_live_snapshot_status.json",
            root=self.settings.root_dir,
        )
        rolling = self.settings.data_dir / "warehouse" / "normalized" / "odds" / f"actionnetwork_all_markets_{date_text}.csv"
        timestamped = sorted(rolling.parent.glob(f"actionnetwork_all_markets_{date_text}_*.csv"))
        raw_root = self.settings.data_dir / "warehouse" / "raw" / "actionnetwork" / "pages" / "snapshots" / date_text
        raw_dirs = sorted([path for path in raw_root.glob("*") if path.is_dir()]) if raw_root.exists() else []
        latest_snapshot = timestamped[-1] if timestamped else None
        stale = not rolling.exists() and str(status.get("status")) in {"missing", "failed"}
        payload = {
            "schemaVersion": "actionnetwork-snapshot-health.v1",
            "status": "stale" if stale else str(status.get("status") or ("fresh" if rolling.exists() else "missing")),
            "ok": bool(rolling.exists() or latest_snapshot or status.get("ok")),
            "date": date_text,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "snapshotFreshness": "fresh" if rolling.exists() else "missing",
            "rollingLatest": _file_info(rolling, self.settings.root_dir),
            "latestTimestampedCsv": _file_info(latest_snapshot, self.settings.root_dir),
            "timestampedCsvCount": len(timestamped),
            "rawSnapshotDirCount": len(raw_dirs),
            "latestRawSnapshotDir": safe_relpath(raw_dirs[-1], self.settings.root_dir) if raw_dirs else "",
            "workflowStatus": status,
            "warnings": [] if rolling.exists() or latest_snapshot else ["No ActionNetwork live-forward snapshot was found for this date."],
        }
        return sanitize_public(payload)

    def label_eligibility(self, *, date_text: str | None = None) -> dict[str, Any]:
        date_text = _date_text(date_text)
        candidates = [
            self.settings.data_dir / "warehouse" / "normalized" / "actionnetwork" / f"actionnetwork_event_confirmed_labels_{date_text}.csv",
            self.settings.data_dir / "warehouse" / "normalized" / "labels" / f"actionnetwork_event_confirmed_labels_{date_text}.csv",
            self.settings.data_dir / "training" / f"actionnetwork_training_{date_text}.csv",
        ]
        rows: list[dict[str, str]] = []
        source = next((path for path in candidates if path.exists()), None)
        if source:
            rows = _read_rows(source)
        summary = _label_summary(rows)
        status = "confirmed" if summary["eventConfirmed"] > 0 and summary["trainableRows"] > 0 else "missing"
        payload = {
            "schemaVersion": "actionnetwork-label-eligibility.v1",
            "status": status,
            "ok": status == "confirmed",
            "date": date_text,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "source": safe_relpath(source, self.settings.root_dir) if source else "",
            "labelQuality": "event_confirmed" if status == "confirmed" else "unavailable",
            "trainableEligibility": "eligible" if status == "confirmed" else "not_trainable",
            **summary,
            "warnings": [] if source else ["No ActionNetwork event-confirmed label file was found for this date."],
        }
        return sanitize_public(payload)

    def trust_summary(self, *, date_text: str | None = None) -> dict[str, Any]:
        snapshot = self.snapshot_health(date_text=date_text)
        labels = self.label_eligibility(date_text=date_text)
        status = "fresh" if snapshot.get("ok") and labels.get("ok") else "degraded"
        return sanitize_public(
            {
                "schemaVersion": "actionnetwork-trust.v1",
                "status": status,
                "ok": status == "fresh",
                "date": snapshot.get("date"),
                "snapshot": snapshot,
                "labels": labels,
                "chips": _chips(snapshot, labels),
            }
        )


def _date_text(value: str | None) -> str:
    if not value or value == "today":
        return date.today().isoformat()
    return str(value)


def _file_info(path: Path | None, root: Path) -> dict[str, Any]:
    if path is None:
        return {"exists": False, "file": ""}
    return {
        "exists": path.exists(),
        "file": safe_relpath(path, root),
        "sizeBytes": path.stat().st_size if path.exists() else 0,
        "modifiedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() if path.exists() else "",
    }


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _label_summary(rows: list[dict[str, str]]) -> dict[str, int]:
    total = len(rows)
    event_confirmed = 0
    trainable = 0
    diagnostic = 0
    date_only = 0
    reused = 0
    push = 0
    for row in rows:
        collection_mode = str(row.get("collection_mode") or row.get("meta_collection_mode") or "")
        bridge_status = str(row.get("bridge_status") or row.get("meta_bridge_status") or "")
        validation_status = str(row.get("validation_status") or "")
        result = str(row.get("label_result") or row.get("target_result") or "")
        if bridge_status == "confirmed" or validation_status == "valid_labeled_event_confirmed":
            event_confirmed += 1
        if collection_mode == "diagnostic_past":
            diagnostic += 1
        if "date_only" in validation_status:
            date_only += 1
        if str(row.get("reused_board_suspect") or row.get("meta_reused_board_suspect") or "0") in {"1", "true", "True"}:
            reused += 1
        if result == "push" or str(row.get("target_push") or "0") in {"1", "true", "True"}:
            push += 1
        excluded = str(row.get("exclude_from_ml") or row.get("target_exclude_from_ml") or "0")
        if excluded == "0" and collection_mode in {"", "live_forward"} and result in {"win", "loss", "0", "1"}:
            trainable += 1
    return {
        "totalRows": total,
        "eventConfirmed": event_confirmed,
        "trainableRows": trainable,
        "diagnosticRows": diagnostic,
        "dateOnlyRows": date_only,
        "reusedBoardRows": reused,
        "pushRows": push,
    }


def _chips(snapshot: dict[str, Any], labels: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": "Snapshot Fresh" if snapshot.get("ok") else "Snapshot Stale", "tone": "good" if snapshot.get("ok") else "risk"},
        {"label": "Event Confirmed" if labels.get("eventConfirmed") else "Not Trainable", "tone": "good" if labels.get("eventConfirmed") else "risk"},
        {"label": labels.get("trainableEligibility", "not_trainable"), "tone": "good" if labels.get("ok") else "watch"},
    ]
