from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings


CONTEXT_STATUSES = {"ok", "partial", "missing", "error", "neutral_fallback"}


@dataclass
class ContextProviderResult:
    status: str
    date: str
    season: int
    source: str
    rows: int
    path: str
    generatedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    externalApiCallsMade: int = 0
    pregameSafe: bool = True
    labelsExcluded: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    criticalForBoard: bool = True

    def __post_init__(self) -> None:
        if self.status not in CONTEXT_STATUSES:
            raise ValueError(f"Unsupported context provider status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "date": self.date,
            "season": int(self.season),
            "source": self.source,
            "rows": int(self.rows),
            "path": self.path,
            "generatedAt": self.generatedAt,
            "externalApiCallsMade": int(self.externalApiCallsMade),
            "pregameSafe": bool(self.pregameSafe),
            "labelsExcluded": bool(self.labelsExcluded),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "criticalForBoard": bool(self.criticalForBoard),
        }


def context_path(settings: Settings, group: str, filename: str) -> Path:
    return settings.data_dir / "context" / group / filename


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        text = str(value).replace("+", "").strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def first_value(row: dict[str, Any], aliases: list[str], default: Any = "") -> Any:
    for alias in aliases:
        value = row.get(alias)
        if clean(value):
            return value
    return default


def key(value: Any) -> str:
    return " ".join(clean(value).lower().split())


def team_key(value: Any) -> str:
    return "".join(ch for ch in clean(value).lower() if ch.isalnum())


def status_for_rows(rows: int, warnings: list[str]) -> str:
    if rows <= 0:
        return "missing"
    return "partial" if warnings else "ok"
