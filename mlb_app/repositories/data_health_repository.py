from __future__ import annotations

from typing import Any

from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean


class DataHealthRepository:
    """Read-only warehouse health and row-count queries."""

    def __init__(self, db: WarehouseDatabase) -> None:
        self.db = db

    def database_status(self, *, season: int | None = None) -> dict[str, Any]:
        health = self.db.health_check().to_dict()
        health.update(
            {
                "latestDbSnapshotDate": "",
                "rowCounts": {},
                "tables": {},
            }
        )
        if not health["enabled"] or not health["reachable"]:
            return health
        summary = self.snapshot_summary(season=season)
        health["latestDbSnapshotDate"] = summary.get("latestDbSnapshotDate", "")
        health["rowCounts"] = summary.get("rowCounts", {})
        health["tables"] = summary.get("tables", {})
        return health

    def snapshot_summary(self, *, season: int | None = None) -> dict[str, Any]:
        row_counts = {
            "collector_runs": self._count("collector_runs"),
            "data_manifests": self._count("data_manifests"),
            "props": self._count("props"),
            "odds_snapshots": self._count("odds_snapshots"),
            "playerboard_snapshots": self._count("playerboard_snapshots", season=season),
            "edge_board_snapshots": self._count("edge_board_snapshots", season=season),
            "research_reports": self._count("research_reports", season=season),
            "model_grades": self._count("model_grades"),
            "audit_events": self._count("audit_events"),
        }
        dates = [
            self._latest_date("playerboard_snapshots", season=season),
            self._latest_date("edge_board_snapshots", season=season),
            self._latest_date("odds_snapshots"),
            self._latest_date("research_reports", season=season),
        ]
        return {
            "latestDbSnapshotDate": max((date for date in dates if date), default=""),
            "rowCounts": row_counts,
            "tables": {
                "playerboardSnapshots": {
                    "latestDate": self._latest_date("playerboard_snapshots", season=season),
                    "marketCounts": self._market_counts("playerboard_snapshots", season=season),
                },
                "edgeBoardSnapshots": {
                    "latestDate": self._latest_date("edge_board_snapshots", season=season),
                    "marketCounts": self._market_counts("edge_board_snapshots", season=season),
                },
                "oddsSnapshots": {
                    "latestDate": self._latest_date("odds_snapshots"),
                    "marketCounts": self._market_counts("odds_snapshots"),
                },
            },
        }

    def _count(self, table: str, *, season: int | None = None) -> int:
        where = ""
        params: dict[str, Any] = {}
        if season is not None and table in {"playerboard_snapshots", "edge_board_snapshots", "research_reports"}:
            where = "WHERE season = :season"
            params["season"] = int(season)
        with self.db.session() as session:
            row = session.fetch_one(f"SELECT COUNT(*) AS row_count FROM {table} {where}", params)
        return int(row.get("row_count") or 0) if row else 0

    def _latest_date(self, table: str, *, season: int | None = None) -> str:
        where = ""
        params: dict[str, Any] = {}
        if season is not None and table in {"playerboard_snapshots", "edge_board_snapshots", "research_reports"}:
            where = "WHERE season = :season"
            params["season"] = int(season)
        with self.db.session() as session:
            row = session.fetch_one(f"SELECT date FROM {table} {where} ORDER BY date DESC LIMIT 1", params)
        return clean(row.get("date")) if row else ""

    def _market_counts(self, table: str, *, season: int | None = None) -> dict[str, int]:
        where = ""
        params: dict[str, Any] = {}
        if season is not None and table in {"playerboard_snapshots", "edge_board_snapshots"}:
            where = "WHERE season = :season"
            params["season"] = int(season)
        with self.db.session() as session:
            rows = session.fetch_all(
                f"""
                SELECT market, COUNT(*) AS row_count
                FROM {table}
                {where}
                GROUP BY market
                ORDER BY market
                """,
                params,
            )
        return {clean(row.get("market")): int(row.get("row_count") or 0) for row in rows if clean(row.get("market"))}
