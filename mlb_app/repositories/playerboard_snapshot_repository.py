from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.playerboard_schema import PLAYERBOARD_FIELDS, PLAYERBOARD_SCHEMA_VERSION, SchemaValidationResult, normalize_market_value
from mlb_app.repositories.playerboard_repository import PlayerboardReadResult
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, date_from_row, first, json_text, market_from_row, optional_float, parse_json_object, stable_id, utc_now_text


class PlayerboardSnapshotRepository:
    """Warehouse repository for historical playerboard rows."""

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
            prop_key = clean(first(row, "propKey", "prop_key", "id")) or _prop_key(row, date_label=row_date)
            row.setdefault("date", row_date)
            row.setdefault("market", market)
            row.setdefault("snapshotAt", snapshot_at)
            values.append(
                {
                    "id": stable_id("playerboard_snapshot", season, row_date, market, prop_key, snapshot_at),
                    "season": int(season),
                    "date": row_date,
                    "snapshot_at": clean(first(row, "snapshotAt", "snapshot_at")) or snapshot_at,
                    "row_index": int(first(row, "rank", "rowIndex") or index),
                    "prop_key": prop_key,
                    "market": market,
                    "player_id": clean(first(row, "playerId", "player_id", "mlbamId")),
                    "player_name": clean(first(row, "player", "playerName", "name")),
                    "team": clean(first(row, "team", "team_abbr", "teamAbbr")).upper(),
                    "opponent": clean(first(row, "opponent", "opponent_abbr", "opponentAbbr")).upper(),
                    "line": clean(first(row, "line", "target", "points")),
                    "book": clean(first(row, "book", "sportsbook", "bestBook", "bookmaker", "sourceBook")),
                    "american_odds": clean(first(row, "americanOdds", "odds", "price")),
                    "model_probability": optional_float(first(row, "modelProbabilityPercent", "finalProbabilityPercent", "probabilityPercent", "probability")),
                    "implied_probability": optional_float(first(row, "impliedProbabilityPercent", "bookImpliedProbabilityPercent", "impliedPercent")),
                    "edge_percent": optional_float(first(row, "edgePercent", "finalEdgePercent", "edge", "modelEdgePercent")),
                    "confidence": clean(first(row, "confidence", "confidenceLabel")),
                    "freshness_status": clean((row.get("freshness") or {}).get("status") if isinstance(row.get("freshness"), dict) else ""),
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
                INSERT INTO playerboard_snapshots(
                  id, season, date, snapshot_at, row_index, prop_key, market, player_id,
                  player_name, team, opponent, line, book, american_odds, model_probability,
                  implied_probability, edge_percent, confidence, freshness_status, source_run_id,
                  source_path, row_json, created_at, updated_at
                ) VALUES (
                  :id, :season, :date, :snapshot_at, :row_index, :prop_key, :market, :player_id,
                  :player_name, :team, :opponent, :line, :book, :american_odds, :model_probability,
                  :implied_probability, :edge_percent, :confidence, :freshness_status, :source_run_id,
                  :source_path, :row_json, :created_at, :updated_at
                )
                ON CONFLICT(date, market, prop_key, snapshot_at) DO UPDATE SET
                  row_index = excluded.row_index,
                  player_id = excluded.player_id,
                  player_name = excluded.player_name,
                  team = excluded.team,
                  opponent = excluded.opponent,
                  line = excluded.line,
                  book = excluded.book,
                  american_odds = excluded.american_odds,
                  model_probability = excluded.model_probability,
                  implied_probability = excluded.implied_probability,
                  edge_percent = excluded.edge_percent,
                  confidence = excluded.confidence,
                  freshness_status = excluded.freshness_status,
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
                SELECT * FROM playerboard_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY row_index ASC, player_name ASC
                """,
                params,
            )

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
                SELECT * FROM playerboard_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY snapshot_at DESC, row_index ASC
                LIMIT :limit
                """,
                params,
            )

    def read_latest_playerboard(
        self,
        *,
        season: int,
        date_label: str = "",
        market: str = "",
        prop_key: str = "",
    ) -> PlayerboardReadResult | None:
        if prop_key:
            row = self._row_by_prop_key(season=season, date_label=date_label, market=market, prop_key=prop_key)
            rows = [row] if row else []
        else:
            rows = self.latest_by_date(season=season, date_label=date_label, market=market)
        if not rows:
            return None
        payload_rows = [_payload_row(row) for row in rows]
        selected_date = clean(rows[0].get("date"))
        source_path = clean(rows[0].get("source_path"))
        snapshot_at = clean(rows[0].get("snapshot_at"))
        validation = SchemaValidationResult(
            ok=True,
            version=PLAYERBOARD_SCHEMA_VERSION,
            observed_fields=tuple(PLAYERBOARD_FIELDS),
        )
        return PlayerboardReadResult(
            path=Path(source_path) if source_path else self.settings.data_dir / "warehouse" / "playerboard_snapshots",
            exists=True,
            validation=validation,
            rows=payload_rows,
            total_rows=len(payload_rows),
            schema_version=PLAYERBOARD_SCHEMA_VERSION,
            source="database",
            snapshot_ids=tuple(clean(row.get("id")) for row in rows if clean(row.get("id"))),
            snapshot_at=snapshot_at,
            selected_date=selected_date,
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
                FROM playerboard_snapshots
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
                f"SELECT date FROM playerboard_snapshots {where} ORDER BY date DESC, snapshot_at DESC LIMIT 1",
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
                SELECT snapshot_at FROM playerboard_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY snapshot_at DESC
                LIMIT 1
                """,
                params,
            )
        return clean(row.get("snapshot_at")) if row else ""

    def _row_by_prop_key(self, *, season: int, date_label: str, market: str, prop_key: str) -> dict[str, Any] | None:
        selected_date = clean(date_label) or self.latest_snapshot_date(season=season)
        if not selected_date:
            return None
        clauses = ["season = :season", "date = :date", "prop_key = :prop_key"]
        params: dict[str, Any] = {"season": int(season), "date": selected_date, "prop_key": prop_key}
        normalized_market = normalize_market_value(market) if market else ""
        if normalized_market:
            clauses.append("market = :market")
            params["market"] = normalized_market
        with self.db.session() as session:
            return session.fetch_one(
                f"""
                SELECT * FROM playerboard_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY snapshot_at DESC
                LIMIT 1
                """,
                params,
            )


def _payload_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = parse_json_object(row.get("row_json"))
    payload.setdefault("date", clean(row.get("date")))
    payload.setdefault("snapshotAt", clean(row.get("snapshot_at")))
    payload.setdefault("market", clean(row.get("market")))
    payload.setdefault("propKey", clean(row.get("prop_key")))
    payload.setdefault("player", clean(row.get("player_name")))
    payload.setdefault("team", clean(row.get("team")))
    payload.setdefault("opponent", clean(row.get("opponent")))
    payload.setdefault("line", clean(row.get("line")))
    payload.setdefault("book", clean(row.get("book")))
    payload.setdefault("americanOdds", clean(row.get("american_odds")))
    return payload


def _prop_key(row: Mapping[str, Any], *, date_label: str) -> str:
    player_identity = clean(first(row, "playerId", "player_id", "mlbamId"))
    if player_identity:
        player_part = f"id:{player_identity}"
    else:
        player = _slug(first(row, "player", "playerName", "name"))
        team = _slug(row.get("team"))
        opponent = _slug(row.get("opponent"))
        player_part = f"name:{player}:{team}:{opponent}"
    parts = [
        date_label,
        player_part,
        _slug(market_from_row(row)),
        clean(first(row, "line", "target", "points")),
        _slug(first(row, "side", "rawLabel", "outcome", "pickSide") or "over"),
        _slug(first(row, "book", "sportsbook", "bestBook", "bookmaker", "sourceBook") or "best_available"),
    ]
    return "|".join(part for part in parts if part)


def _slug(value: Any) -> str:
    text = clean(value).lower()
    return "-".join(part for part in text.replace("|", " ").split() if part)
