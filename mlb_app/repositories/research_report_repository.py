from __future__ import annotations

from typing import Any, Mapping

from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, first, json_text, parse_json_object, stable_id, utc_now_text


class ResearchReportRepository:
    """Warehouse repository for generated research report payloads."""

    def __init__(self, db: WarehouseDatabase) -> None:
        self.db = db

    def upsert_report(
        self,
        payload: Mapping[str, Any],
        *,
        season: int,
        date_label: str,
        report_key: str = "daily",
        generated_at: str = "",
        source_snapshot_id: str = "",
    ) -> int:
        generated_at = clean(generated_at or first(payload, "generatedAt", "generated_at")) or utc_now_text()
        now = utc_now_text()
        values = {
            "id": stable_id("research_report", season, date_label, report_key, generated_at),
            "season": int(season),
            "date": date_label,
            "report_key": report_key,
            "generated_at": generated_at,
            "source_snapshot_id": source_snapshot_id,
            "payload_json": json_text(dict(payload), {}),
            "created_at": now,
            "updated_at": now,
        }
        with self.db.session(write=True) as session:
            session.execute(
                """
                INSERT INTO research_reports(
                  id, season, date, report_key, generated_at, source_snapshot_id,
                  payload_json, created_at, updated_at
                ) VALUES (
                  :id, :season, :date, :report_key, :generated_at, :source_snapshot_id,
                  :payload_json, :created_at, :updated_at
                )
                ON CONFLICT(date, report_key, generated_at) DO UPDATE SET
                  season = excluded.season,
                  source_snapshot_id = excluded.source_snapshot_id,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )
        return 1

    def latest_by_date(self, *, season: int, date_label: str = "", report_key: str = "daily") -> dict[str, Any] | None:
        clauses = ["season = :season", "report_key = :report_key"]
        params: dict[str, Any] = {"season": int(season), "report_key": report_key}
        if date_label:
            clauses.append("date = :date")
            params["date"] = date_label
        with self.db.session() as session:
            row = session.fetch_one(
                f"""
                SELECT * FROM research_reports
                WHERE {' AND '.join(clauses)}
                ORDER BY date DESC, generated_at DESC
                LIMIT 1
                """,
                params,
            )
        return row

    def latest_payload(self, *, season: int, date_label: str = "", report_key: str = "daily") -> dict[str, Any] | None:
        row = self.latest_by_date(season=season, date_label=date_label, report_key=report_key)
        if not row:
            return None
        payload = parse_json_object(row.get("payload_json"))
        if not payload:
            return None
        source = dict(payload.get("source") or {})
        source["database"] = {
            "table": "research_reports",
            "id": clean(row.get("id")),
            "generatedAt": clean(row.get("generated_at")),
        }
        payload["source"] = source
        return payload

    def historical_by_date(self, *, season: int, date_label: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.session() as session:
            return session.fetch_all(
                """
                SELECT * FROM research_reports
                WHERE season = :season AND date = :date
                ORDER BY generated_at DESC
                LIMIT :limit
                """,
                {"season": int(season), "date": date_label, "limit": int(max(1, min(limit, 500)))},
            )
