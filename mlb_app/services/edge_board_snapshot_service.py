from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.edge_board_service import EdgeBoardService

MAX_CSV_ROWS = 10000


@dataclass(frozen=True)
class EdgeBoardSnapshotResult:
    json_path: Path
    csv_path: Path | None
    row_count: int
    date: str
    season: int


class EdgeBoardSnapshotService:
    """Persist collector-built EdgeBoard snapshots without changing the API route."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        edge_board_service: Any | None = None,
        edge_board_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.edge_board_service = edge_board_service or EdgeBoardService()
        self.edge_board_dir = Path(edge_board_dir or settings.data_dir / "edge_board")

    def write_snapshot(self, *, date_label: str, season: int, limit: int = 5000) -> EdgeBoardSnapshotResult:
        query = {
            "date": [date_label],
            "season": [str(int(season))],
            "limit": [str(int(limit))],
        }
        payload = self.edge_board_service.payload(query)
        rows = [row for row in payload.get("rows") or [] if isinstance(row, dict)]
        snapshot_payload = {
            **payload,
            "snapshot": {
                "source": "season_auto_collector",
                "date": date_label,
                "season": int(season),
                "writtenAt": datetime.now(timezone.utc).isoformat(),
                "rowCount": len(rows),
            },
        }

        self.edge_board_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.edge_board_dir / f"edge_board_{date_label}.json"
        _atomic_write_text(json_path, json.dumps(snapshot_payload, indent=2, ensure_ascii=False))

        csv_path: Path | None = None
        if rows:
            csv_path = self.edge_board_dir / f"edge_board_{date_label}.csv"
            _write_rows_csv(csv_path, rows[:MAX_CSV_ROWS])

        return EdgeBoardSnapshotResult(
            json_path=json_path,
            csv_path=csv_path,
            row_count=len(rows),
            date=date_label,
            season=int(season),
        )


def _atomic_write_text(path: Path, content: str) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(str(key))

    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})
    tmp_path.replace(path)
