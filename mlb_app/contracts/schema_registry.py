from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlb_app.contracts.playerboard_schema import (
    PLAYERBOARD_FIELDS,
    PLAYERBOARD_SCHEMA_VERSION,
    PlayerboardSchemaError,
    SchemaValidationResult,
    normalize_playerboard_row,
    validate_playerboard_header,
)


@dataclass(frozen=True)
class SchemaDefinition:
    name: str
    version: str
    fields: tuple[str, ...]
    can_read: bool = True
    can_write: bool = False


@dataclass(frozen=True)
class SchemaMigrationResult:
    source_version: str
    target_version: str
    rows: list[dict[str, Any]]
    warnings: tuple[str, ...] = ()


class PlayerboardSchemaRegistry:
    """Small contract registry for current and legacy playerboard schemas."""

    def __init__(self) -> None:
        self.current = SchemaDefinition(
            name="playerboard",
            version=PLAYERBOARD_SCHEMA_VERSION,
            fields=tuple(PLAYERBOARD_FIELDS),
            can_read=True,
            can_write=True,
        )
        # Legacy schemas are field-name compatible when required fields exist.
        # They are migrated by filling optional/computed fields through the
        # playerboard row normalizer.
        self.legacy_versions: tuple[str, ...] = ("playerboard.legacy.v2",)

    def validate(self, header: list[str], *, strict: bool = False) -> SchemaValidationResult:
        result = validate_playerboard_header(header)
        if strict and (not result.ok or result.version != self.current.version or result.extra_fields):
            raise PlayerboardSchemaError(result)
        if not result.ok:
            raise PlayerboardSchemaError(result)
        return result

    def detect_version(self, header: list[str]) -> str:
        return validate_playerboard_header(header).version

    def migrate_rows(
        self,
        header: list[str],
        rows: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> SchemaMigrationResult:
        result = self.validate(header, strict=strict)
        migrated = [normalize_playerboard_row(row) for row in rows]
        return SchemaMigrationResult(
            source_version=result.version,
            target_version=self.current.version,
            rows=migrated,
            warnings=result.warnings,
        )


PLAYERBOARD_SCHEMA_REGISTRY = PlayerboardSchemaRegistry()
