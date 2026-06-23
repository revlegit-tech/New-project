from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.runtime_status_service import safe_relpath


def file_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return int(max(0.0, (datetime.now(timezone.utc) - modified).total_seconds()))


def count_csv_rows(path: Path) -> int | None:
    if not path.exists() or path.suffix.lower() != ".csv":
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except Exception:
        return None


class DataFreshnessService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def payload(self, date_text: str | None = None) -> dict[str, Any]:
        date_text = date_text or datetime.now().strftime("%Y-%m-%d")
        paths = {
            "actionnetwork_latest": self.settings.data_dir / "warehouse" / "normalized" / "odds" / f"actionnetwork_all_markets_{date_text}.csv",
            "playerboard": self.settings.data_dir / "playerboard" / f"playerboard_{self.settings.current_season}.csv",
            "edge_board": self.settings.data_dir / "edge_board" / f"edge_board_{date_text}.json",
        }
        sources = {name: self._source_status(path) for name, path in paths.items()}
        missing = [name for name, item in sources.items() if item["status"] == "missing"]
        return {
            "schemaVersion": "data-freshness.v1",
            "status": "degraded" if missing else "ok",
            "ok": not missing,
            "date": date_text,
            "sources": sources,
            "warnings": [f"Missing {name}." for name in missing],
        }

    def _source_status(self, path: Path) -> dict[str, Any]:
        exists = path.exists()
        return {
            "status": "present" if exists else "missing",
            "exists": exists,
            "file": safe_relpath(path, self.settings.root_dir),
            "ageSeconds": file_age_seconds(path),
            "rowCount": count_csv_rows(path),
        }
