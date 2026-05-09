from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.playerboard_schema import normalize_market_value, normalize_playerboard_row
from mlb_app.repositories.db import SQLiteDatabase, utc_now


class BoardRowRepository:
    """SQLite repository for indexed playerboard rows.

    ``row_json`` preserves the existing PlayerboardSnapshot row contract while
    normalized columns make the serving hot path fast for common prop-detail
    and board filters.  This repository never reads or parses playerboard CSVs.
    """

    def __init__(self, runtime_settings: Settings | None = None, *, db: SQLiteDatabase | None = None) -> None:
        self.settings = runtime_settings or default_settings
        self.db = db or SQLiteDatabase(self.settings.state_db_path)
        self.db.initialize()

    @property
    def path(self) -> Path:
        return self.db.path

    def bulk_insert(
        self,
        *,
        connection: Any,
        snapshot_id: str,
        rows: Sequence[dict[str, Any]],
        season: int,
        date_label: str,
    ) -> int:
        """Insert all rows for a new board snapshot using the caller transaction."""

        now = utc_now()
        inserted = 0
        for index, row in enumerate(rows):
            values = _row_values(
                snapshot_id=snapshot_id,
                row_index=index,
                row=row,
                season=season,
                date_label=date_label,
                created_at=now,
            )
            connection.execute(
                """
                INSERT INTO board_rows(
                  snapshot_id,
                  row_index,
                  prop_key,
                  season,
                  date,
                  market,
                  player_id,
                  player_name,
                  team,
                  opponent,
                  pitcher,
                  line,
                  side,
                  book,
                  american_odds,
                  edge_percent,
                  probability_percent,
                  implied_probability_percent,
                  rank_score,
                  row_json,
                  created_at
                ) VALUES (
                  :snapshot_id,
                  :row_index,
                  :prop_key,
                  :season,
                  :date,
                  :market,
                  :player_id,
                  :player_name,
                  :team,
                  :opponent,
                  :pitcher,
                  :line,
                  :side,
                  :book,
                  :american_odds,
                  :edge_percent,
                  :probability_percent,
                  :implied_probability_percent,
                  :rank_score,
                  :row_json,
                  :created_at
                )
                """,
                values,
            )
            inserted += 1
        return inserted

    def list_rows_for_snapshot(
        self,
        snapshot_id: str,
        *,
        market: str = "",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["snapshot_id = ?"]
        params: list[Any] = [snapshot_id]
        normalized_market = normalize_market_value(market) if market else ""
        if normalized_market:
            clauses.append("market = ?")
            params.append(normalized_market)
        sql = f"SELECT row_json FROM board_rows WHERE {' AND '.join(clauses)} ORDER BY row_index ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))
        rows = self.db.fetch_all(sql, tuple(params))
        return [_payload_from_row(row) for row in rows]

    def row_for_prop_key(self, snapshot_id: str, prop_key: str) -> dict[str, Any] | None:
        row = self.db.fetch_one(
            "SELECT row_json FROM board_rows WHERE snapshot_id = ? AND prop_key = ? LIMIT 1",
            (snapshot_id, str(prop_key or "")),
        )
        return _payload_from_row(row) if row else None

    def find_active_row_by_prop_key(
        self,
        *,
        season: int,
        date_label: str,
        market: str = "",
        prop_key: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Return an indexed prop-key row plus its active snapshot metadata."""

        normalized_market = normalize_market_value(market) if market else ""
        params: list[Any] = [int(season), str(date_label or ""), str(prop_key or "")]
        market_clause = ""
        if normalized_market:
            # Prefer an exact-market active snapshot, then fall back to an
            # all-market active snapshot that contains the requested row.
            market_clause = "AND s.market IN (?, '') AND r.market = ?"
            params.extend([normalized_market, normalized_market])
        row = self.db.fetch_one(
            f"""
            SELECT
              r.row_json AS row_json,
              s.id AS snapshot_id,
              s.season AS season,
              s.date AS date,
              s.market AS snapshot_market,
              s.snapshot_at AS snapshot_at,
              s.schema_version AS schema_version,
              s.row_count AS row_count,
              s.csv_path AS csv_path,
              s.metadata_json AS metadata_json
            FROM board_rows r
            JOIN board_snapshots s ON s.id = r.snapshot_id
            WHERE s.status = 'active'
              AND s.season = ?
              AND s.date = ?
              AND r.prop_key = ?
              {market_clause}
            ORDER BY CASE WHEN s.market = ? THEN 0 WHEN s.market = '' THEN 1 ELSE 2 END, s.snapshot_at DESC
            LIMIT 1
            """,
            tuple(params + [normalized_market]),
        )
        if not row:
            return None
        return _payload_from_row(row), dict(row)


def _row_values(
    *,
    snapshot_id: str,
    row_index: int,
    row: dict[str, Any],
    season: int,
    date_label: str,
    created_at: str,
) -> dict[str, Any]:
    contract_row = {**row, "season": row.get("season") or season, "date": row.get("date") or date_label}
    for json_field in ("books", "missingData", "hitRates", "recentGames"):
        value = contract_row.get(json_field)
        if isinstance(value, (dict, list)):
            contract_row[json_field] = json.dumps(value, ensure_ascii=False)
    normalized = normalize_playerboard_row(contract_row)
    normalized["propKey"] = str(row.get("propKey") or _prop_key_for_row(normalized))
    normalized.setdefault("id", normalized["propKey"])
    market = normalize_market_value(normalized.get("market"))
    edge = _optional_float(normalized.get("finalEdgePercent") or normalized.get("edgePercent"))
    probability = _optional_float(normalized.get("finalProbabilityPercent") or normalized.get("modelProbabilityPercent"))
    implied = _optional_float(normalized.get("impliedProbabilityPercent") or normalized.get("sportsbookImpliedPercent"))
    return {
        "snapshot_id": snapshot_id,
        "row_index": int(row_index),
        "prop_key": normalized["propKey"],
        "season": int(normalized.get("season") or season),
        "date": str(normalized.get("date") or date_label),
        "market": market,
        "player_id": _optional_text(_first(normalized, "playerId", "player_id", "mlbamId")),
        "player_name": _optional_text(_first(normalized, "player", "playerName", "name")),
        "team": _optional_text(normalized.get("team")),
        "opponent": _optional_text(normalized.get("opponent")),
        "pitcher": _optional_text(normalized.get("pitcher")),
        "line": _optional_text(normalized.get("line")),
        "side": _detail_side(normalized),
        "book": _optional_text(_first(normalized, "book", "sportsbook", "bestBook", "bookmaker", "sourceBook")),
        "american_odds": _optional_text(_first(normalized, "americanOdds", "odds", "price")),
        "edge_percent": edge,
        "probability_percent": probability,
        "implied_probability_percent": implied,
        "rank_score": edge if edge is not None else probability,
        "row_json": json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
        "created_at": created_at,
    }


def _payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(row.get("row_json") or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any) -> str:
    text = _clean(value).lower()
    return "-".join(part for part in text.replace("|", " ").split() if part)


def _detail_side(row: dict[str, Any]) -> str:
    label = _clean(row.get("rawLabel") or row.get("side") or row.get("outcome")).casefold()
    market = _clean(row.get("market")).lower()
    player = _clean(row.get("player")).casefold()
    if "under" in label or label in {"no", "n"}:
        return "under"
    if "over" in label or label in {"yes", "y"}:
        return "over"
    if player and player in label:
        return "over"
    if market.startswith(("batter_", "pitcher_")):
        return "over"
    return label or "over"


def _prop_key_for_row(row: dict[str, Any]) -> str:
    player_identity = _clean(_first(row, "playerId", "player_id", "mlbamId"))
    if player_identity:
        player_part = f"id:{player_identity}"
    else:
        player = _slug(_first(row, "player", "playerName", "name"))
        team = _slug(row.get("team"))
        opponent = _slug(row.get("opponent"))
        player_part = f"name:{player}:{team}:{opponent}"

    parts = [
        _clean(row.get("date")),
        player_part,
        _slug(row.get("market")),
        _clean(row.get("line")),
        _slug(_detail_side(row)),
        _slug(_first(row, "book", "sportsbook", "bestBook", "bookmaker", "sourceBook") or "best_available"),
    ]
    return "|".join(part for part in parts if part)
