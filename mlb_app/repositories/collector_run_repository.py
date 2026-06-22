from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, first, json_text, stable_id, utc_now_text


class CollectorRunRepository:
    """Warehouse persistence for collector run manifests."""

    def __init__(self, db: WarehouseDatabase) -> None:
        self.db = db

    def upsert(self, run: Mapping[str, Any]) -> int:
        now = utc_now_text()
        run_id = clean(first(run, "run_id", "runId", "workflow_run_id", "workflowRunId")) or stable_id(
            "collector_run",
            first(run, "date", "current_date"),
            first(run, "finished_at", "finishedAt", "generated_at"),
        )
        payload = {
            "id": stable_id("collector_run", run_id),
            "run_id": run_id,
            "date": clean(first(run, "date", "current_date")),
            "run_type": clean(first(run, "run_type", "runType")),
            "status": clean(first(run, "status", "freshness_status")) or ("success" if bool(run.get("success")) else ""),
            "started_at": clean(first(run, "started_at", "startedAt")),
            "finished_at": clean(first(run, "finished_at", "finishedAt", "generated_at")),
            "provider": clean(first(run, "provider")) or "propline",
            "props_loaded": int(first(run.get("source_counts") or {}, "propCount", "propsLoaded") or run.get("props_loaded") or 0),
            "playerboard_rows": int(first(run, "playerboard_rows", "playerboardRows") or 0),
            "edge_board_rows": int(first(run, "edge_board_rows", "edgeBoardRows") or 0),
            "artifact_name": clean(first(run, "artifact_name", "artifactName")),
            "manifest_path": clean(first(run, "manifest_path", "manifestPath")),
            "warnings_json": json_text(run.get("warnings") or [], []),
            "errors_json": json_text(run.get("errors") or [], []),
            "payload_json": json_text(dict(run), {}),
            "created_at": now,
            "updated_at": now,
        }
        with self.db.session(write=True) as session:
            session.execute(
                """
                INSERT INTO collector_runs(
                  id, run_id, date, run_type, status, started_at, finished_at, provider,
                  props_loaded, playerboard_rows, edge_board_rows, artifact_name, manifest_path,
                  warnings_json, errors_json, payload_json, created_at, updated_at
                ) VALUES (
                  :id, :run_id, :date, :run_type, :status, :started_at, :finished_at, :provider,
                  :props_loaded, :playerboard_rows, :edge_board_rows, :artifact_name, :manifest_path,
                  :warnings_json, :errors_json, :payload_json, :created_at, :updated_at
                )
                ON CONFLICT(run_id) DO UPDATE SET
                  date = excluded.date,
                  run_type = excluded.run_type,
                  status = excluded.status,
                  started_at = excluded.started_at,
                  finished_at = excluded.finished_at,
                  provider = excluded.provider,
                  props_loaded = excluded.props_loaded,
                  playerboard_rows = excluded.playerboard_rows,
                  edge_board_rows = excluded.edge_board_rows,
                  artifact_name = excluded.artifact_name,
                  manifest_path = excluded.manifest_path,
                  warnings_json = excluded.warnings_json,
                  errors_json = excluded.errors_json,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                payload,
            )
        return 1

    def upsert_manifest(self, manifest: Mapping[str, Any], *, manifest_path: str | Path = "") -> int:
        enriched = dict(manifest)
        if manifest_path:
            enriched["manifest_path"] = str(manifest_path)
        self.upsert(enriched)
        now = utc_now_text()
        path = clean(manifest_path or first(enriched, "manifest_path", "manifestPath"))
        if not path:
            path = stable_id("manifest_path", first(enriched, "run_id", "runId"), first(enriched, "date"))
        values = {
            "id": stable_id("data_manifest", path),
            "run_id": clean(first(enriched, "run_id", "runId")),
            "date": clean(first(enriched, "date", "current_date")),
            "manifest_path": path,
            "payload_json": json_text(enriched, {}),
            "created_at": now,
            "updated_at": now,
        }
        with self.db.session(write=True) as session:
            session.execute(
                """
                INSERT INTO data_manifests(id, run_id, date, manifest_path, payload_json, created_at, updated_at)
                VALUES (:id, :run_id, :date, :manifest_path, :payload_json, :created_at, :updated_at)
                ON CONFLICT(manifest_path) DO UPDATE SET
                  run_id = excluded.run_id,
                  date = excluded.date,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )
        return 1

    def latest_by_date(self, date_label: str = "") -> dict[str, Any] | None:
        if date_label:
            sql = """
                SELECT * FROM collector_runs
                WHERE date = :date
                ORDER BY finished_at DESC, updated_at DESC
                LIMIT 1
            """
            params = {"date": date_label}
        else:
            sql = "SELECT * FROM collector_runs ORDER BY date DESC, finished_at DESC, updated_at DESC LIMIT 1"
            params = {}
        with self.db.session() as session:
            return session.fetch_one(sql, params)

    def historical_by_date(self, date_label: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.session() as session:
            return session.fetch_all(
                """
                SELECT * FROM collector_runs
                WHERE date = :date
                ORDER BY finished_at DESC, updated_at DESC
                LIMIT :limit
                """,
                {"date": date_label, "limit": int(max(1, min(limit, 500)))},
            )
