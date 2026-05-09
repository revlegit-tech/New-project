from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SQL_PARAMS = Sequence[Any] | Mapping[str, Any]
_DEFAULT_MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_INIT_LOCK = threading.RLock()
_INITIALIZED: set[Path] = set()


class DatabaseError(RuntimeError):
    """Raised when the transactional state store cannot be initialized or queried."""


class SQLiteDatabase:
    """Small SQLite helper for app-owned mutable state.

    The repository layer opens short-lived connections rather than sharing one
    global connection across request threads. Each connection is configured for
    WAL mode, foreign keys, and a busy timeout before use.
    """

    def __init__(self, path: Path | str, *, migrations_dir: Path | str | None = None) -> None:
        self.path = Path(path).resolve()
        self.migrations_dir = Path(migrations_dir or _DEFAULT_MIGRATIONS_DIR).resolve()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        self._configure(connection)
        return connection

    def initialize(self) -> None:
        """Run all pending migrations once per process for this database path."""

        with _INIT_LOCK:
            if self.path in _INITIALIZED:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as connection:
                self._ensure_migration_table(connection)
                applied = self._applied_versions(connection)
                for migration in sorted(self.migrations_dir.glob("*.sql")):
                    version = migration.stem
                    if version in applied:
                        continue
                    script = migration.read_text(encoding="utf-8")
                    try:
                        connection.execute("BEGIN IMMEDIATE")
                        for statement in _sql_statements(script):
                            connection.execute(statement)
                        connection.execute(
                            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                            (version, utc_now()),
                        )
                        connection.execute("COMMIT")
                    except sqlite3.Error as error:
                        if connection.in_transaction:
                            connection.execute("ROLLBACK")
                        raise DatabaseError(f"Failed to apply migration {version}: {error}") from error
            _INITIALIZED.add(self.path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside an IMMEDIATE transaction."""

        self.initialize()
        connection = self.connect()
        started_at = time.perf_counter()
        outcome = "ok"
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            outcome = "error"
            connection.execute("ROLLBACK")
            raise
        finally:
            _observe_sqlite_write_latency(self.path, started_at, outcome)
            connection.close()

    def fetch_one(self, sql: str, params: _SQL_PARAMS = ()) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: _SQL_PARAMS = ()) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def execute(self, sql: str, params: _SQL_PARAMS = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(sql, params)
            return cursor.rowcount

    def migration_versions(self) -> list[str]:
        self.initialize()
        rows = self.fetch_all("SELECT version FROM schema_migrations ORDER BY version")
        return [str(row["version"]) for row in rows]

    @staticmethod
    def _configure(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")

    @staticmethod
    def _ensure_migration_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _applied_versions(connection: sqlite3.Connection) -> set[str]:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
        return {str(row["version"]) for row in rows}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sql_statements(script: str) -> list[str]:
    # Migration files in this project are DDL-only and avoid semicolons inside
    # strings/triggers. Splitting keeps migration application inside the same
    # explicit transaction instead of using sqlite3.executescript(), which
    # auto-commits before execution.
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def _observe_sqlite_write_latency(path: Path, started_at: float, outcome: str) -> None:
    try:
        from mlb_app.observability.metrics import default_registry

        default_registry().observe(
            "sqlite_write_latency_ms",
            round((time.perf_counter() - started_at) * 1000.0, 3),
            labels={"database": path.name, "outcome": outcome},
        )
    except Exception:
        # Metrics must never break transactional state.
        return
