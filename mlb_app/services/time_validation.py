from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Sequence

LEAKAGE_COLUMN_TOKENS: tuple[str, ...] = (
    "actual",
    "result",
    "graded",
    "grade_",
    "postgame",
    "boxscore",
    "final_",
    "close_",  # only allowed if the prediction timestamp is after close; fail by default
    "settled",
    "win_loss",
    "profit",
    "roi",
)


@dataclass(frozen=True)
class ChronologicalSplit:
    train_rows: list[dict[str, Any]]
    validation_rows: list[dict[str, Any]]
    train_start: date | None
    train_end: date | None
    validation_start: date | None
    validation_end: date | None

    def metadata(self) -> dict[str, Any]:
        return {
            "strategy": "chronological",
            "trainRows": len(self.train_rows),
            "validationRows": len(self.validation_rows),
            "trainStart": self.train_start.isoformat() if self.train_start else "",
            "trainEnd": self.train_end.isoformat() if self.train_end else "",
            "validationStart": self.validation_start.isoformat() if self.validation_start else "",
            "validationEnd": self.validation_end.isoformat() if self.validation_end else "",
        }


def parse_date_value(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        raise ValueError("Missing date value")
    return datetime.fromisoformat(text[:10]).date()


def chronological_train_validation_split(
    rows: Iterable[dict[str, Any]],
    *,
    date_column: str = "date",
    validation_fraction: float = 0.2,
    embargo_days: int = 0,
) -> ChronologicalSplit:
    dated_rows = [(parse_date_value(row.get(date_column)), row) for row in rows]
    if not dated_rows:
        return ChronologicalSplit([], [], None, None, None, None)
    dated_rows.sort(key=lambda item: item[0])
    unique_dates = sorted({item[0] for item in dated_rows})
    if len(unique_dates) < 2:
        raise ValueError("Chronological validation requires at least two distinct dates")
    validation_date_count = max(1, int(round(len(unique_dates) * validation_fraction)))
    validation_start = unique_dates[-validation_date_count]
    train_cutoff = validation_start - timedelta(days=embargo_days)

    train_rows = [row for row_date, row in dated_rows if row_date < train_cutoff]
    validation_rows = [row for row_date, row in dated_rows if row_date >= validation_start]
    if not train_rows or not validation_rows:
        raise ValueError("Chronological split produced an empty train or validation set")

    train_dates = [parse_date_value(row[date_column]) for row in train_rows]
    validation_dates = [parse_date_value(row[date_column]) for row in validation_rows]
    return ChronologicalSplit(
        train_rows=train_rows,
        validation_rows=validation_rows,
        train_start=min(train_dates),
        train_end=max(train_dates),
        validation_start=min(validation_dates),
        validation_end=max(validation_dates),
    )


def find_leakage_columns(
    columns: Sequence[str],
    *,
    allowed_columns: set[str] | None = None,
    denied_tokens: Sequence[str] = LEAKAGE_COLUMN_TOKENS,
) -> list[str]:
    allowed = {column.lower() for column in (allowed_columns or set())}
    leaks: list[str] = []
    for column in columns:
        lowered = column.lower()
        if lowered in allowed:
            continue
        if any(token in lowered for token in denied_tokens):
            leaks.append(column)
    return leaks


def assert_no_postgame_leakage(columns: Sequence[str], *, allowed_columns: set[str] | None = None) -> None:
    leaks = find_leakage_columns(columns, allowed_columns=allowed_columns)
    if leaks:
        joined = ", ".join(sorted(leaks))
        raise ValueError(f"Potential postgame/leakage columns are not allowed at prediction time: {joined}")
