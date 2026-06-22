from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from mlb_app.contracts.playerboard_schema import normalize_market_value
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, date_from_row, first, json_text, market_from_row, optional_float, stable_id, utc_now_text


class PropRepository:
    """Warehouse repository for normalized props and odds snapshots."""

    def __init__(self, db: WarehouseDatabase) -> None:
        self.db = db

    def upsert_props(self, rows: Sequence[Mapping[str, Any]], *, source_path: str | Path = "") -> int:
        now = utc_now_text()
        values = []
        for raw in rows:
            row = dict(raw)
            date_label = date_from_row(row)
            market = normalize_market_value(market_from_row(row))
            source_prop_key = clean(first(row, "source_prop_key", "sourcePropKey", "source_prop_id", "sourcePropId", "id"))
            if not source_prop_key:
                source_prop_key = stable_id(
                    "prop_key",
                    date_label,
                    market,
                    first(row, "player", "playerName", "name"),
                    first(row, "team"),
                    first(row, "opponent"),
                    first(row, "line", "target", "points"),
                    first(row, "side", "outcome", "rawLabel"),
                    first(row, "book", "sportsbook", "bookmaker"),
                )
            values.append(
                {
                    "id": stable_id("prop", source_prop_key),
                    "source_prop_key": source_prop_key,
                    "date": date_label,
                    "game_id": clean(first(row, "game_id", "gameId", "source_event_id", "sourceEventId")),
                    "player_id": clean(first(row, "player_id", "playerId", "mlbamId")),
                    "player_name": clean(first(row, "player", "playerName", "name")),
                    "team": clean(first(row, "team", "team_abbr", "teamAbbr")).upper(),
                    "opponent": clean(first(row, "opponent", "opponent_abbr", "opponentAbbr")).upper(),
                    "market": market,
                    "line": clean(first(row, "line", "target", "points")),
                    "side": clean(first(row, "side", "outcome", "rawLabel")),
                    "book": clean(first(row, "book", "sportsbook", "bookmaker", "sourceBook")),
                    "american_odds": clean(first(row, "americanOdds", "odds", "price")),
                    "implied_probability": optional_float(first(row, "impliedProbability", "impliedProbabilityPercent", "impliedPercent")),
                    "source": clean(first(row, "source", "provider")) or "csv",
                    "source_event_id": clean(first(row, "source_event_id", "sourceEventId", "event_id", "eventId")),
                    "source_prop_id": clean(first(row, "source_prop_id", "sourcePropId", "prop_id", "propId")),
                    "collected_at": clean(first(row, "collected_at", "collectedAt", "snapshotAt", "snapshot_at")),
                    "raw_file_id": str(source_path or ""),
                    "payload_json": json_text(row, {}),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if not values:
            return 0
        with self.db.session(write=True) as session:
            return session.executemany(
                """
                INSERT INTO props(
                  id, source_prop_key, date, game_id, player_id, player_name, team, opponent,
                  market, line, side, book, american_odds, implied_probability, source,
                  source_event_id, source_prop_id, collected_at, raw_file_id, payload_json,
                  created_at, updated_at
                ) VALUES (
                  :id, :source_prop_key, :date, :game_id, :player_id, :player_name, :team, :opponent,
                  :market, :line, :side, :book, :american_odds, :implied_probability, :source,
                  :source_event_id, :source_prop_id, :collected_at, :raw_file_id, :payload_json,
                  :created_at, :updated_at
                )
                ON CONFLICT(source_prop_key) DO UPDATE SET
                  date = excluded.date,
                  game_id = excluded.game_id,
                  player_id = excluded.player_id,
                  player_name = excluded.player_name,
                  team = excluded.team,
                  opponent = excluded.opponent,
                  market = excluded.market,
                  line = excluded.line,
                  side = excluded.side,
                  book = excluded.book,
                  american_odds = excluded.american_odds,
                  implied_probability = excluded.implied_probability,
                  source = excluded.source,
                  source_event_id = excluded.source_event_id,
                  source_prop_id = excluded.source_prop_id,
                  collected_at = excluded.collected_at,
                  raw_file_id = excluded.raw_file_id,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )

    def upsert_odds_snapshots(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        snapshot_at: str,
        source_path: str | Path = "",
    ) -> int:
        now = utc_now_text()
        values = []
        for raw in rows:
            row = dict(raw)
            date_label = date_from_row(row)
            market = normalize_market_value(market_from_row(row))
            row_snapshot_at = clean(first(row, "snapshotAt", "snapshot_at", "collectedAt", "collected_at")) or snapshot_at
            source_snapshot_key = clean(first(row, "source_snapshot_key", "sourceSnapshotKey", "id"))
            if not source_snapshot_key:
                source_snapshot_key = stable_id(
                    "odds_snapshot_key",
                    date_label,
                    row_snapshot_at,
                    market,
                    first(row, "player", "playerName", "name"),
                    first(row, "team"),
                    first(row, "opponent"),
                    first(row, "line", "target", "points"),
                    first(row, "side", "outcome", "rawLabel"),
                    first(row, "book", "sportsbook", "bookmaker"),
                )
            values.append(
                {
                    "id": stable_id("odds_snapshot", source_snapshot_key),
                    "source_snapshot_key": source_snapshot_key,
                    "date": date_label,
                    "snapshot_at": row_snapshot_at,
                    "market": market,
                    "player_name": clean(first(row, "player", "playerName", "name")),
                    "team": clean(first(row, "team", "team_abbr", "teamAbbr")).upper(),
                    "opponent": clean(first(row, "opponent", "opponent_abbr", "opponentAbbr")).upper(),
                    "line": clean(first(row, "line", "target", "points")),
                    "side": clean(first(row, "side", "outcome", "rawLabel")),
                    "book": clean(first(row, "book", "sportsbook", "bookmaker", "sourceBook")),
                    "american_odds": clean(first(row, "americanOdds", "odds", "price")),
                    "implied_probability": optional_float(first(row, "impliedProbability", "impliedProbabilityPercent", "impliedPercent")),
                    "source_path": str(source_path or ""),
                    "payload_json": json_text(row, {}),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if not values:
            return 0
        with self.db.session(write=True) as session:
            return session.executemany(
                """
                INSERT INTO odds_snapshots(
                  id, source_snapshot_key, date, snapshot_at, market, player_name, team,
                  opponent, line, side, book, american_odds, implied_probability,
                  source_path, payload_json, created_at, updated_at
                ) VALUES (
                  :id, :source_snapshot_key, :date, :snapshot_at, :market, :player_name, :team,
                  :opponent, :line, :side, :book, :american_odds, :implied_probability,
                  :source_path, :payload_json, :created_at, :updated_at
                )
                ON CONFLICT(source_snapshot_key) DO UPDATE SET
                  date = excluded.date,
                  snapshot_at = excluded.snapshot_at,
                  market = excluded.market,
                  player_name = excluded.player_name,
                  team = excluded.team,
                  opponent = excluded.opponent,
                  line = excluded.line,
                  side = excluded.side,
                  book = excluded.book,
                  american_odds = excluded.american_odds,
                  implied_probability = excluded.implied_probability,
                  source_path = excluded.source_path,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )

    def latest_by_date(self, *, date_label: str = "", market: str = "", limit: int = 500) -> list[dict[str, Any]]:
        selected_date = date_label or self.latest_snapshot_date()
        if not selected_date:
            return []
        clauses = ["date = :date"]
        params: dict[str, Any] = {"date": selected_date, "limit": int(max(1, min(limit, 5000)))}
        if market:
            clauses.append("market = :market")
            params["market"] = normalize_market_value(market)
        with self.db.session() as session:
            return session.fetch_all(
                f"""
                SELECT * FROM odds_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY snapshot_at DESC, player_name ASC
                LIMIT :limit
                """,
                params,
            )

    def historical_by_date(self, *, date_label: str, market: str = "", limit: int = 1000) -> list[dict[str, Any]]:
        return self.latest_by_date(date_label=date_label, market=market, limit=limit)

    def row_counts_by_market_date(self, *, date_label: str = "") -> dict[str, int]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if date_label:
            clauses.append("date = :date")
            params["date"] = date_label
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.session() as session:
            rows = session.fetch_all(
                f"""
                SELECT market, COUNT(*) AS row_count
                FROM odds_snapshots
                {where}
                GROUP BY market
                ORDER BY market
                """,
                params,
            )
        return {clean(row.get("market")): int(row.get("row_count") or 0) for row in rows}

    def latest_snapshot_date(self) -> str:
        with self.db.session() as session:
            row = session.fetch_one("SELECT date FROM odds_snapshots ORDER BY date DESC, snapshot_at DESC LIMIT 1")
        return clean(row.get("date")) if row else ""
