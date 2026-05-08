from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DataContract:
    name: str
    path_glob: str
    required_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()
    min_rows: int = 1


@dataclass(frozen=True)
class ContractResult:
    name: str
    path: str
    status: str
    row_count: int = 0
    missing_columns: tuple[str, ...] = ()
    type_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def default_contracts(season: int) -> tuple[DataContract, ...]:
    return (
        DataContract(
            name="playerboard",
            path_glob=f"data/playerboard/playerboard_{season}.csv",
            required_columns=("date", "market", "player", "team", "line"),
            numeric_columns=("line",),
            date_columns=("date",),
            min_rows=1,
        ),
        DataContract(
            name="playerboard_backtest",
            path_glob=f"data/backtests/playerboard_backtest_{season}.csv",
            required_columns=("date", "market", "player", "team", "line", "result"),
            numeric_columns=("line",),
            date_columns=("date",),
            min_rows=1,
        ),
        DataContract(
            name="prediction_history",
            path_glob="data/predictions/*.csv",
            required_columns=("createdAt", "market", "player", "line", "probability"),
            numeric_columns=("line", "probability"),
            min_rows=0,
        ),
        DataContract(
            name="batter_logs",
            path_glob=f"data/cloud/season_logs/batter_game_logs_{season}.csv",
            required_columns=("date", "player", "team"),
            date_columns=("date",),
            min_rows=1,
        ),
        DataContract(
            name="pitcher_logs",
            path_glob=f"data/cloud/season_logs/pitcher_game_logs_{season}.csv",
            required_columns=("date", "player", "team"),
            date_columns=("date",),
            min_rows=1,
        ),
        DataContract(
            name="weather_features",
            path_glob=f"data/cache/weather/weather_features_{season}.csv",
            required_columns=("gamePk",),
            min_rows=0,
        ),
    )


def _read_rows(path: Path, limit: int = 250) -> tuple[list[str], list[dict[str, str]], int]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        total = 0
        for row in reader:
            total += 1
            if len(rows) < limit:
                rows.append({str(key): str(value or "") for key, value in row.items()})
    return fieldnames, rows, total


def _is_number(value: str) -> bool:
    if value == "":
        return True
    try:
        float(value)
    except ValueError:
        return False
    return True


def _is_iso_date(value: str) -> bool:
    if value == "":
        return True
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def validate_contract(root: Path, contract: DataContract) -> list[ContractResult]:
    matches = sorted(root.glob(contract.path_glob))
    if not matches:
        status = "ok" if contract.min_rows == 0 else "missing"
        return [ContractResult(name=contract.name, path=contract.path_glob, status=status)]

    results: list[ContractResult] = []
    for path in matches:
        try:
            columns, rows, row_count = _read_rows(path)
        except OSError as error:
            results.append(ContractResult(name=contract.name, path=str(path), status="failed", warnings=(str(error),)))
            continue

        missing = tuple(column for column in contract.required_columns if column not in columns)
        type_errors: list[str] = []
        if not missing:
            for idx, row in enumerate(rows, start=2):
                for column in contract.numeric_columns:
                    if column in row and not _is_number(row[column]):
                        type_errors.append(f"row {idx}: {column} must be numeric")
                for column in contract.date_columns:
                    if column in row and not _is_iso_date(row[column]):
                        type_errors.append(f"row {idx}: {column} must be ISO date")

        warnings: list[str] = []
        if row_count < contract.min_rows:
            warnings.append(f"expected at least {contract.min_rows} rows, found {row_count}")

        status = "ok"
        if missing or type_errors:
            status = "failed"
        elif warnings:
            status = "partial"

        results.append(
            ContractResult(
                name=contract.name,
                path=str(path),
                status=status,
                row_count=row_count,
                missing_columns=missing,
                type_errors=tuple(type_errors),
                warnings=tuple(warnings),
            )
        )
    return results


def validate_contracts(root: Path, contracts: Iterable[DataContract]) -> list[ContractResult]:
    results: list[ContractResult] = []
    for contract in contracts:
        results.extend(validate_contract(root, contract))
    return results
