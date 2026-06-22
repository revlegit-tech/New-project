from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.playerboard_schema import normalize_market_value
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, date_from_row, first, json_text, market_from_row, optional_float, parse_json_object, stable_id, utc_now_text


class EdgeBoardSnapshotRepository:
    """Warehouse repository for persisted EdgeBoard snapshots."""

    def __init__(self, db: WarehouseDatabase, *, settings: Settings = default_settings) -> None:
        self.db = db
        self.settings = settings

    def upsert_snapshot(
        self,
        *,
        season: int,
        date_label: str,
        rows: Sequence[Mapping[str, Any]],
        snapshot_at: str,
        source_path: str | Path = "",
        source_run_id: str = "",
    ) -> int:
        now = utc_now_text()
        values = []
        for index, raw in enumerate(rows):
            row = dict(raw)
            row_date = date_from_row(row, date_label)
            market = normalize_market_value(market_from_row(row))
            prop_key = clean(first(row, "propKey", "prop_key", "id")) or stable_id(
                "edge_prop",
                row_date,
                market,
                first(row, "player", "playerName", "team"),
                first(row, "line"),
                first(row, "book", "americanOdds"),
            )
            row.setdefault("date", row_date)
            row.setdefault("market", market)
            row.setdefault("snapshotAt", snapshot_at)
            values.append(
                {
                    "id": stable_id("edge_board_snapshot", season, row_date, market, prop_key, snapshot_at),
                    "season": int(season),
                    "date": row_date,
                    "snapshot_at": clean(first(row, "snapshotAt", "snapshot_at")) or snapshot_at,
                    "row_index": int(first(row, "rank", "rowIndex") or index),
                    "prop_key": prop_key,
                    "market": market,
                    "player_name": clean(first(row, "player", "playerName", "name")),
                    "team": clean(first(row, "team", "team_abbr", "teamAbbr")).upper(),
                    "opponent": clean(first(row, "opponent", "opponent_abbr", "opponentAbbr")).upper(),
                    "edge_percent": optional_float(first(row, "edgePercent", "finalEdgePercent", "edge")),
                    "score": optional_float(first(row, "score", "rankScore")),
                    "decision_label": clean(first(row, "decisionLabel", "recommendation")),
                    "source_run_id": clean(source_run_id),
                    "source_path": str(source_path or ""),
                    "row_json": json_text(row, {}),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if not values:
            return 0
        with self.db.session(write=True) as session:
            return session.executemany(
                """
                INSERT INTO edge_board_snapshots(
                  id, season, date, snapshot_at, row_index, prop_key, market, player_name,
                  team, opponent, edge_percent, score, decision_label, source_run_id,
                  source_path, row_json, created_at, updated_at
                ) VALUES (
                  :id, :season, :date, :snapshot_at, :row_index, :prop_key, :market, :player_name,
                  :team, :opponent, :edge_percent, :score, :decision_label, :source_run_id,
                  :source_path, :row_json, :created_at, :updated_at
                )
                ON CONFLICT(date, market, prop_key, snapshot_at) DO UPDATE SET
                  row_index = excluded.row_index,
                  player_name = excluded.player_name,
                  team = excluded.team,
                  opponent = excluded.opponent,
                  edge_percent = excluded.edge_percent,
                  score = excluded.score,
                  decision_label = excluded.decision_label,
                  source_run_id = excluded.source_run_id,
                  source_path = excluded.source_path,
                  row_json = excluded.row_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )

    def latest_by_date(self, *, season: int, date_label: str = "", market: str = "") -> list[dict[str, Any]]:
        selected_date = clean(date_label) or self.latest_snapshot_date(season=season)
        if not selected_date:
            return []
        normalized_market = normalize_market_value(market) if market else ""
        latest = self._latest_snapshot_at(season=season, date_label=selected_date, market=normalized_market)
        if not latest:
            return []
        clauses = ["season = :season", "date = :date", "snapshot_at = :snapshot_at"]
        params: dict[str, Any] = {"season": int(season), "date": selected_date, "snapshot_at": latest}
        if normalized_market:
            clauses.append("market = :market")
            params["market"] = normalized_market
        with self.db.session() as session:
            return session.fetch_all(
                f"""
                SELECT * FROM edge_board_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY row_index ASC, score DESC, player_name ASC
                """,
                params,
            )

    def latest_rows(self, *, season: int, date_label: str = "", market: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = self.latest_by_date(season=season, date_label=date_label, market=market)
        if not rows:
            return [], {}
        return [_payload_row(row) for row in rows], {
            "date": clean(rows[0].get("date")),
            "snapshotAt": clean(rows[0].get("snapshot_at")),
            "sourcePath": clean(rows[0].get("source_path")),
            "snapshotIds": [clean(row.get("id")) for row in rows if clean(row.get("id"))],
        }

    def historical_by_date(self, *, season: int, date_label: str, market: str = "", limit: int = 1000) -> list[dict[str, Any]]:
        normalized_market = normalize_market_value(market) if market else ""
        clauses = ["season = :season", "date = :date"]
        params: dict[str, Any] = {"season": int(season), "date": date_label, "limit": int(max(1, min(limit, 5000)))}
        if normalized_market:
            clauses.append("market = :market")
            params["market"] = normalized_market
        with self.db.session() as session:
            return session.fetch_all(
                f"""
                SELECT * FROM edge_board_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY snapshot_at DESC, row_index ASC
                LIMIT :limit
                """,
                params,
            )

    def row_counts_by_market_date(self, *, season: int, date_label: str = "") -> dict[str, int]:
        clauses = ["season = :season"]
        params: dict[str, Any] = {"season": int(season)}
        if date_label:
            clauses.append("date = :date")
            params["date"] = date_label
        with self.db.session() as session:
            rows = session.fetch_all(
                f"""
                SELECT market, COUNT(*) AS row_count
                FROM edge_board_snapshots
                WHERE {' AND '.join(clauses)}
                GROUP BY market
                ORDER BY market
                """,
                params,
            )
        return {clean(row.get("market")): int(row.get("row_count") or 0) for row in rows}

    def latest_snapshot_date(self, *, season: int | None = None) -> str:
        params: dict[str, Any] = {}
        where = ""
        if season is not None:
            where = "WHERE season = :season"
            params["season"] = int(season)
        with self.db.session() as session:
            row = session.fetch_one(
                f"SELECT date FROM edge_board_snapshots {where} ORDER BY date DESC, snapshot_at DESC LIMIT 1",
                params,
            )
        return clean(row.get("date")) if row else ""

    def _latest_snapshot_at(self, *, season: int, date_label: str, market: str = "") -> str:
        clauses = ["season = :season", "date = :date"]
        params: dict[str, Any] = {"season": int(season), "date": date_label}
        if market:
            clauses.append("market = :market")
            params["market"] = market
        with self.db.session() as session:
            row = session.fetch_one(
                f"""
                SELECT snapshot_at FROM edge_board_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY snapshot_at DESC
                LIMIT 1
                """,
                params,
            )
        return clean(row.get("snapshot_at")) if row else ""


def _payload_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = parse_json_object(row.get("row_json"))
    payload.setdefault("date", clean(row.get("date")))
    payload.setdefault("snapshotAt", clean(row.get("snapshot_at")))
    payload.setdefault("market", clean(row.get("market")))
    payload.setdefault("propKey", clean(row.get("prop_key")))
    payload.setdefault("player", clean(row.get("player_name")))
    payload.setdefault("team", clean(row.get("team")))
    payload.setdefault("opponent", clean(row.get("opponent")))
    payload.setdefault("decisionLabel", clean(row.get("decision_label")))
    return payload
