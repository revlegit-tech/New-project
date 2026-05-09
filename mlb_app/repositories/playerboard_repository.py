from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.playerboard_schema import (
    PLAYERBOARD_FIELDS,
    PLAYERBOARD_SCHEMA_VERSION,
    PlayerboardSchemaError,
    SchemaValidationResult,
    normalize_market_value,
    normalize_playerboard_row,
    validate_playerboard_header,
)
from mlb_app.contracts.schema_registry import PLAYERBOARD_SCHEMA_REGISTRY


@dataclass(frozen=True)
class PlayerboardReadResult:
    path: Path
    exists: bool
    validation: SchemaValidationResult
    rows: list[dict[str, Any]]
    total_rows: int
    schema_version: str = PLAYERBOARD_SCHEMA_VERSION


class PlayerboardRepository:
    """Read/write boundary for saved Playerboard CSV snapshots.

    CSV remains an interchange/export format in Sprint 2. The repository owns
    path resolution, header validation, and safe legacy normalization so service
    code does not know raw file details.
    """

    def __init__(self, settings: Settings = default_settings, playerboard_dir: Path | None = None) -> None:
        self.settings = settings
        self.playerboard_dir = Path(playerboard_dir) if playerboard_dir else settings.data_dir / "playerboard"

    def path_for_season(self, season: int) -> Path:
        return self.playerboard_dir / f"playerboard_{int(season)}.csv"

    def header_for_path(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                return [str(value).strip() for value in next(reader)]
            except StopIteration:
                return []

    def validate_path(self, path: Path) -> SchemaValidationResult:
        if not path.exists():
            return SchemaValidationResult(
                ok=True,
                version=PLAYERBOARD_SCHEMA_VERSION,
                reason="file_missing",
                observed_fields=(),
            )
        return validate_playerboard_header(self.header_for_path(path))

    def read_raw_rows(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def read_current_playerboard(
        self,
        *,
        season: int,
        date_label: str = "",
        market: str = "",
        strict: bool = False,
    ) -> PlayerboardReadResult:
        path = self.path_for_season(season)
        if not path.exists():
            validation = self.validate_path(path)
            return PlayerboardReadResult(path=path, exists=False, validation=validation, rows=[], total_rows=0)

        header = self.header_for_path(path)
        raw_rows = self.read_raw_rows(path)
        try:
            migration = PLAYERBOARD_SCHEMA_REGISTRY.migrate_rows(header, raw_rows, strict=strict)
            validation = validate_playerboard_header(header)
            normalized_rows = migration.rows
        except PlayerboardSchemaError as exc:
            if strict:
                raise
            return PlayerboardReadResult(
                path=path,
                exists=True,
                validation=exc.result,
                rows=[],
                total_rows=len(raw_rows),
                schema_version=exc.result.version,
            )

        target_date = str(date_label or "").strip()
        target_market = normalize_market_value(market) if market else ""
        rows: list[dict[str, Any]] = []
        for row in normalized_rows:
            if target_date and str(row.get("date") or "").strip() != target_date:
                continue
            if target_market and normalize_market_value(row.get("market")) != target_market:
                continue
            rows.append(row)

        return PlayerboardReadResult(
            path=path,
            exists=True,
            validation=validation,
            rows=rows,
            total_rows=len(raw_rows),
            schema_version=PLAYERBOARD_SCHEMA_VERSION,
        )

    def write_snapshot_rows(
        self,
        *,
        season: int,
        rows: list[dict[str, Any]],
        replace: bool = False,
    ) -> Path:
        """Explicit pipeline write operation used by collectors/builders.

        Services should call read methods only. Builder/pipeline code can opt in
        to this write method to keep mutation points visible.
        """

        path = self.path_for_season(season)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if replace or not path.exists() else "a"
        with path.open(mode, encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=PLAYERBOARD_FIELDS)
            if mode == "w":
                writer.writeheader()
            for row in rows:
                normalized = normalize_playerboard_row(row)
                writer.writerow({field: _csv_contract_value(field, normalized.get(field, "")) for field in PLAYERBOARD_FIELDS})
        return path


def _csv_contract_value(field: str, value: Any) -> Any:
    if field in {"books", "missingData", "hitRates", "recentGames"}:
        if isinstance(value, str):
            return value
        return json.dumps(value or [], ensure_ascii=False)
    if value is None:
        return ""
    return value
