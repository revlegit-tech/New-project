from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.db import utc_now

_SQL_PARAMS = Mapping[str, Any] | Sequence[Any] | None
_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"


class WarehouseDatabaseError(RuntimeError):
    """Raised when the optional historical warehouse cannot be queried."""


@dataclass(frozen=True)
class WarehouseHealth:
    enabled: bool
    reachable: bool
    dialect: str
    fallback_to_csv: bool
    reason: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "reachable": self.reachable,
            "dialect": self.dialect,
            "fallbackToCsv": self.fallback_to_csv,
            "reason": self.reason,
            "error": self.error,
        }


class WarehouseSession:
    """Tiny DB-API session wrapper with named-parameter SQL helpers."""

    def __init__(self, connection: Any, *, dialect: str, echo: bool = False) -> None:
        self.connection = connection
        self.dialect = dialect
        self.echo = echo

    def execute(self, sql: str, params: _SQL_PARAMS = None) -> Any:
        statement = self._prepare_sql(sql)
        values = params or {}
        if self.echo:
            print(statement)
        return self.connection.execute(statement, values)

    def fetch_one(self, sql: str, params: _SQL_PARAMS = None) -> dict[str, Any] | None:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return _row_to_dict(row)

    def fetch_all(self, sql: str, params: _SQL_PARAMS = None) -> list[dict[str, Any]]:
        cursor = self.execute(sql, params)
        return [_row_to_dict(row) or {} for row in cursor.fetchall()]

    def executemany(self, sql: str, rows: Sequence[Mapping[str, Any]]) -> int:
        if not rows:
            return 0
        statement = self._prepare_sql(sql)
        if self.echo:
            print(statement)
        if hasattr(self.connection, "executemany"):
            cursor = self.connection.executemany(statement, rows)
        else:
            cursor = self.connection.cursor()
            cursor.executemany(statement, rows)
        rowcount = getattr(cursor, "rowcount", 0)
        return int(rowcount if rowcount is not None and rowcount >= 0 else len(rows))

    def _prepare_sql(self, sql: str) -> str:
        if self.dialect != "postgresql":
            return sql
        return re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql)


class WarehouseDatabase:
    """Optional historical DB connection factory for Sprint 13 data.

    The app's existing SQLite state store remains separate. This class is for
    production-grade MLB collector/playerboard/edge-board history and stays
    dormant unless DB_ENABLED and DATABASE_URL are configured.
    """

    def __init__(
        self,
        database_url: str = "",
        *,
        enabled: bool = False,
        pool_size: int = 5,
        echo: bool = False,
        fallback_to_csv: bool = True,
        migrations_dir: Path | str | None = None,
    ) -> None:
        self.database_url = str(database_url or "").strip()
        self.enabled = bool(enabled)
        self.pool_size = int(pool_size or 5)
        self.echo = bool(echo)
        self.fallback_to_csv = bool(fallback_to_csv)
        self.migrations_dir = Path(migrations_dir or _MIGRATIONS_DIR)

    @classmethod
    def from_settings(cls, settings: Settings = default_settings) -> "WarehouseDatabase":
        return cls(
            settings.database_url,
            enabled=settings.db_enabled,
            pool_size=settings.database_pool_size,
            echo=settings.database_echo,
            fallback_to_csv=settings.db_fallback_to_csv,
        )

    @property
    def dialect(self) -> str:
        if not self.database_url:
            return ""
        scheme = urlparse(self.database_url).scheme.lower()
        if scheme.startswith("postgres"):
            return "postgresql"
        if scheme in {"sqlite", "sqlite3"}:
            return "sqlite"
        return scheme

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.database_url)

    @contextmanager
    def session(self, *, write: bool = False) -> Iterator[WarehouseSession]:
        if not self.enabled:
            raise WarehouseDatabaseError("warehouse database is disabled")
        if not self.database_url:
            raise WarehouseDatabaseError("DATABASE_URL is not configured")
        dialect = self.dialect
        connection = self._connect(dialect)
        session = WarehouseSession(connection, dialect=dialect, echo=self.echo)
        started = False
        try:
            if write:
                if dialect == "sqlite":
                    connection.execute("BEGIN")
                started = True
            yield session
            if write:
                connection.commit()
        except Exception:
            if write and started:
                connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Apply dialect-specific migrations for the optional warehouse DB."""

        if not self.configured:
            raise WarehouseDatabaseError("warehouse database is not configured")
        dialect = self.dialect
        migration_root = self.migrations_dir / dialect
        if not migration_root.exists():
            raise WarehouseDatabaseError(f"no migrations found for dialect {dialect}")
        with self.session(write=True) as session:
            session.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version TEXT PRIMARY KEY,
                  applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                str(row["version"])
                for row in session.fetch_all("SELECT version FROM schema_migrations")
                if row.get("version")
            }
            for migration in sorted(migration_root.glob("*.sql")):
                version = migration.stem
                if version in applied:
                    continue
                for statement in _sql_statements(migration.read_text(encoding="utf-8")):
                    session.execute(statement)
                session.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (:version, :applied_at)",
                    {"version": version, "applied_at": utc_now()},
                )

    def health_check(self) -> WarehouseHealth:
        if not self.enabled:
            return WarehouseHealth(
                enabled=False,
                reachable=False,
                dialect=self.dialect,
                fallback_to_csv=self.fallback_to_csv,
                reason="disabled",
            )
        if not self.database_url:
            return WarehouseHealth(
                enabled=True,
                reachable=False,
                dialect="",
                fallback_to_csv=self.fallback_to_csv,
                reason="missing_database_url",
            )
        try:
            with self.session() as session:
                session.fetch_one("SELECT 1 AS ok")
            return WarehouseHealth(
                enabled=True,
                reachable=True,
                dialect=self.dialect,
                fallback_to_csv=self.fallback_to_csv,
                reason="ok",
            )
        except Exception as error:
            return WarehouseHealth(
                enabled=True,
                reachable=False,
                dialect=self.dialect,
                fallback_to_csv=self.fallback_to_csv,
                reason="unreachable",
                error=f"{type(error).__name__}: {error}",
            )

    def _connect(self, dialect: str) -> Any:
        if dialect == "sqlite":
            path = _sqlite_path_from_url(self.database_url)
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            return connection
        if dialect == "postgresql":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as error:
                raise WarehouseDatabaseError(
                    "PostgreSQL DATABASE_URL requires psycopg. Install psycopg[binary] in production."
                ) from error
            return psycopg.connect(self.database_url, row_factory=dict_row)
        raise WarehouseDatabaseError(f"unsupported DATABASE_URL scheme: {dialect or '<missing>'}")


def _sqlite_path_from_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.path in {"", "/"}:
        raise WarehouseDatabaseError("sqlite DATABASE_URL must include a path")
    if parsed.path == "/:memory:":
        return ":memory:"
    path = unquote(parsed.path).replace("\\", "/")
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return path


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def _sql_statements(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]
