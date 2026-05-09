from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.playerboard_schema import PLAYERBOARD_FIELDS, PLAYERBOARD_SCHEMA_VERSION, SchemaValidationResult, normalize_market_value
from mlb_app.repositories.board_row_repository import BoardRowRepository
from mlb_app.repositories.db import SQLiteDatabase, utc_now
from mlb_app.repositories.playerboard_repository import PlayerboardReadResult


@dataclass(frozen=True)
class BoardSnapshotRecord:
    id: str
    season: int
    date: str
    market: str
    snapshot_at: str
    status: str
    source: str
    source_mode: str
    schema_version: str
    row_count: int
    csv_path: str
    metadata: dict[str, Any]


class BoardSnapshotRepository:
    """Repository for SQLite-backed serving snapshots.

    Snapshots are written as pending, their rows are inserted in the same
    SQLite transaction, previous active snapshots for the affected scope are
    deactivated, and the new snapshot is promoted to active as the final write.
    Readers only see fully materialized active snapshots.
    """

    def __init__(
        self,
        runtime_settings: Settings | None = None,
        *,
        db: SQLiteDatabase | None = None,
        row_repository: BoardRowRepository | None = None,
    ) -> None:
        self.settings = runtime_settings or default_settings
        self.db = db or SQLiteDatabase(self.settings.state_db_path)
        self.db.initialize()
        self.rows = row_repository or BoardRowRepository(self.settings, db=self.db)

    @property
    def path(self) -> Path:
        return self.db.path

    def replace_active_snapshot(
        self,
        *,
        season: int,
        date_label: str,
        rows: Sequence[dict[str, Any]],
        market: str = "",
        snapshot_at: str = "",
        source: str = "pipeline",
        source_mode: str = "",
        csv_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BoardSnapshotRecord:
        """Atomically materialize and activate a serving snapshot."""

        normalized_market = normalize_market_value(market) if market else ""
        snapshot_at = str(snapshot_at or utc_now())
        created_at = utc_now()
        snapshot_id = _snapshot_id(
            season=season,
            date_label=date_label,
            market=normalized_market,
            snapshot_at=snapshot_at,
            rows=rows,
        )
        metadata_payload = dict(metadata or {})
        metadata_payload.setdefault("rowCount", len(rows))
        values = {
            "id": snapshot_id,
            "season": int(season),
            "date": str(date_label or ""),
            "market": normalized_market,
            "snapshot_at": snapshot_at,
            "status": "pending",
            "source": str(source or "pipeline"),
            "source_mode": str(source_mode or ""),
            "schema_version": PLAYERBOARD_SCHEMA_VERSION,
            "row_count": int(len(rows)),
            "csv_path": str(csv_path or ""),
            "active_at": None,
            "created_at": created_at,
            "updated_at": created_at,
            "metadata_json": json.dumps(metadata_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
        }
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO board_snapshots(
                  id,
                  season,
                  date,
                  market,
                  snapshot_at,
                  status,
                  source,
                  source_mode,
                  schema_version,
                  row_count,
                  csv_path,
                  active_at,
                  created_at,
                  updated_at,
                  metadata_json
                ) VALUES (
                  :id,
                  :season,
                  :date,
                  :market,
                  :snapshot_at,
                  :status,
                  :source,
                  :source_mode,
                  :schema_version,
                  :row_count,
                  :csv_path,
                  :active_at,
                  :created_at,
                  :updated_at,
                  :metadata_json
                )
                """,
                values,
            )
            inserted = self.rows.bulk_insert(
                connection=connection,
                snapshot_id=snapshot_id,
                rows=rows,
                season=season,
                date_label=date_label,
            )
            if inserted != len(rows):
                raise RuntimeError(f"board snapshot row-count mismatch: expected {len(rows)}, inserted {inserted}")

            active_at = utc_now()
            if normalized_market:
                connection.execute(
                    """
                    UPDATE board_snapshots
                    SET status = 'inactive', updated_at = ?
                    WHERE status = 'active' AND season = ? AND date = ? AND market = ?
                    """,
                    (active_at, int(season), str(date_label or ""), normalized_market),
                )
            else:
                # A full-board snapshot supersedes all active per-market slices
                # for that slate. Per-market rebuilds after this point can still
                # become exact-market active overlays.
                connection.execute(
                    """
                    UPDATE board_snapshots
                    SET status = 'inactive', updated_at = ?
                    WHERE status = 'active' AND season = ? AND date = ?
                    """,
                    (active_at, int(season), str(date_label or "")),
                )
            connection.execute(
                """
                UPDATE board_snapshots
                SET status = 'active', active_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (active_at, active_at, snapshot_id),
            )

        record = self.get(snapshot_id)
        if record is None:
            raise RuntimeError(f"activated board snapshot could not be reloaded: {snapshot_id}")
        return record

    def get(self, snapshot_id: str) -> BoardSnapshotRecord | None:
        row = self.db.fetch_one("SELECT * FROM board_snapshots WHERE id = ?", (snapshot_id,))
        return _snapshot_record(row) if row else None

    def activate_snapshot(self, snapshot_id: str) -> BoardSnapshotRecord:
        """Promote an existing materialized snapshot back to active."""

        record = self.get(snapshot_id)
        if record is None:
            raise KeyError(f"board snapshot not found: {snapshot_id}")
        active_at = utc_now()
        with self.db.transaction() as connection:
            if record.market:
                connection.execute(
                    """
                    UPDATE board_snapshots
                    SET status = 'inactive', updated_at = ?
                    WHERE status = 'active' AND season = ? AND date = ? AND market = ?
                    """,
                    (active_at, record.season, record.date, record.market),
                )
            else:
                connection.execute(
                    """
                    UPDATE board_snapshots
                    SET status = 'inactive', updated_at = ?
                    WHERE status = 'active' AND season = ? AND date = ?
                    """,
                    (active_at, record.season, record.date),
                )
            connection.execute(
                """
                UPDATE board_snapshots
                SET status = 'active', active_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (active_at, active_at, snapshot_id),
            )
        activated = self.get(snapshot_id)
        if activated is None:
            raise KeyError(f"board snapshot not found after activation: {snapshot_id}")
        return activated

    def list_snapshots(self, *, season: int | None = None, date_label: str = "", limit: int = 50) -> list[BoardSnapshotRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if season is not None:
            clauses.append("season = ?")
            params.append(int(season))
        if date_label:
            clauses.append("date = ?")
            params.append(str(date_label))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        rows = self.db.fetch_all(
            f"SELECT * FROM board_snapshots {where} ORDER BY created_at DESC, snapshot_at DESC LIMIT ?",
            tuple(params),
        )
        return [_snapshot_record(row) for row in rows]

    def active_snapshots(self, *, season: int, date_label: str = "", market: str = "") -> list[BoardSnapshotRecord]:
        selected_date = str(date_label or self.latest_active_date(season) or "")
        if not selected_date:
            return []
        normalized_market = normalize_market_value(market) if market else ""
        if normalized_market:
            rows = self.db.fetch_all(
                """
                SELECT * FROM board_snapshots
                WHERE status = 'active' AND season = ? AND date = ? AND market = ?
                ORDER BY snapshot_at DESC
                """,
                (int(season), selected_date, normalized_market),
            )
            if not rows:
                rows = self.db.fetch_all(
                    """
                    SELECT * FROM board_snapshots
                    WHERE status = 'active' AND season = ? AND date = ? AND market = ''
                    ORDER BY snapshot_at DESC
                    LIMIT 1
                    """,
                    (int(season), selected_date),
                )
            return [_snapshot_record(row) for row in rows]

        rows = self.db.fetch_all(
            """
            SELECT * FROM board_snapshots
            WHERE status = 'active' AND season = ? AND date = ?
            ORDER BY CASE WHEN market = '' THEN 1 ELSE 0 END, market ASC, snapshot_at DESC
            """,
            (int(season), selected_date),
        )
        records = [_snapshot_record(row) for row in rows]
        # If a full-board active snapshot coexists with newer exact-market
        # overlays, the read path includes both; row filtering below removes the
        # overlaid markets from the full snapshot.
        return records

    def latest_active_date(self, season: int) -> str:
        row = self.db.fetch_one(
            """
            SELECT date FROM board_snapshots
            WHERE status = 'active' AND season = ?
            ORDER BY date DESC, snapshot_at DESC
            LIMIT 1
            """,
            (int(season),),
        )
        return str(row.get("date") or "") if row else ""

    def read_active_playerboard(
        self,
        *,
        season: int,
        date_label: str = "",
        market: str = "",
        prop_key: str = "",
    ) -> PlayerboardReadResult | None:
        """Return a PlayerboardRepository-compatible read result from SQLite."""

        selected_date = str(date_label or self.latest_active_date(season) or "")
        if not selected_date:
            return None
        normalized_market = normalize_market_value(market) if market else ""

        if prop_key:
            indexed = self.rows.find_active_row_by_prop_key(
                season=int(season),
                date_label=selected_date,
                market=normalized_market,
                prop_key=prop_key,
            )
            if indexed:
                row_payload, meta = indexed
                record = _snapshot_record(
                    {
                        "id": meta.get("snapshot_id"),
                        "season": meta.get("season"),
                        "date": meta.get("date"),
                        "market": meta.get("snapshot_market"),
                        "snapshot_at": meta.get("snapshot_at"),
                        "status": "active",
                        "source": "sqlite",
                        "source_mode": "",
                        "schema_version": meta.get("schema_version") or PLAYERBOARD_SCHEMA_VERSION,
                        "row_count": meta.get("row_count") or 1,
                        "csv_path": meta.get("csv_path") or "",
                        "metadata_json": meta.get("metadata_json") or "{}",
                    }
                )
                return self._read_result_from_records([record], [row_payload], selected_date=selected_date)

        records = self.active_snapshots(season=int(season), date_label=selected_date, market=normalized_market)
        if not records:
            return None

        exact_markets = {record.market for record in records if record.market}
        rows: list[dict[str, Any]] = []
        for record in records:
            record_market = normalized_market if normalized_market and not record.market else ""
            snapshot_rows = self.rows.list_rows_for_snapshot(record.id, market=record_market)
            if not normalized_market and record.market == "" and exact_markets:
                snapshot_rows = [row for row in snapshot_rows if normalize_market_value(row.get("market")) not in exact_markets]
            rows.extend(snapshot_rows)
        return self._read_result_from_records(records, rows, selected_date=selected_date)

    def _read_result_from_records(
        self,
        records: Sequence[BoardSnapshotRecord],
        rows: list[dict[str, Any]],
        *,
        selected_date: str,
    ) -> PlayerboardReadResult:
        latest_record = max(records, key=lambda record: record.snapshot_at)
        validation = SchemaValidationResult(
            ok=True,
            version=latest_record.schema_version or PLAYERBOARD_SCHEMA_VERSION,
            observed_fields=tuple(PLAYERBOARD_FIELDS),
        )
        return PlayerboardReadResult(
            path=self.db.path,
            exists=True,
            validation=validation,
            rows=rows,
            total_rows=sum(record.row_count for record in records),
            schema_version=latest_record.schema_version or PLAYERBOARD_SCHEMA_VERSION,
            source="sqlite",
            snapshot_ids=tuple(record.id for record in records),
            snapshot_at=latest_record.snapshot_at,
            selected_date=selected_date,
        )


def _snapshot_record(row: dict[str, Any]) -> BoardSnapshotRecord:
    try:
        metadata = json.loads(str(row.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    return BoardSnapshotRecord(
        id=str(row.get("id") or ""),
        season=int(row.get("season") or 0),
        date=str(row.get("date") or ""),
        market=normalize_market_value(row.get("market")) if row.get("market") else "",
        snapshot_at=str(row.get("snapshot_at") or ""),
        status=str(row.get("status") or ""),
        source=str(row.get("source") or ""),
        source_mode=str(row.get("source_mode") or ""),
        schema_version=str(row.get("schema_version") or PLAYERBOARD_SCHEMA_VERSION),
        row_count=int(row.get("row_count") or 0),
        csv_path=str(row.get("csv_path") or ""),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _snapshot_id(*, season: int, date_label: str, market: str, snapshot_at: str, rows: Sequence[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    digest.update(str(season).encode("utf-8"))
    digest.update(b"|")
    digest.update(str(date_label or "").encode("utf-8"))
    digest.update(b"|")
    digest.update(str(market or "").encode("utf-8"))
    digest.update(b"|")
    digest.update(str(snapshot_at or "").encode("utf-8"))
    digest.update(b"|")
    digest.update(str(len(rows)).encode("utf-8"))
    for row in rows[:10]:
        digest.update(json.dumps(row, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8"))
    return f"board_snapshot_{digest.hexdigest()[:24]}"
