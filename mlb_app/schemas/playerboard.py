from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerboardStatus:
    latest_date: str
    rows_loaded: int
    total_rows: int
    schema_status: str
    latest_fully_graded_date: str = ""
