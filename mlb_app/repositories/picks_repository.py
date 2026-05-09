from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.db import SQLiteDatabase

PickMutator = Callable[[dict[str, Any]], dict[str, Any]]


class PickNotFoundError(KeyError):
    """Raised when an update targets a pick id that is not in SQLite."""


class PicksRepository:
    """SQLite-backed repository for user-tracked picks.

    The normalized columns are used for transactional queries and auditability;
    ``metadata_json`` preserves the current API payload shape so existing UI code
    can migrate without a breaking contract change.
    """

    def __init__(self, runtime_settings: Settings | None = None, *, db: SQLiteDatabase | None = None) -> None:
        self.settings = runtime_settings or default_settings
        self.db = db or SQLiteDatabase(self.settings.state_db_path)
        self.db.initialize()

    @property
    def path(self) -> Path:
        return self.db.path

    def count(self) -> int:
        row = self.db.fetch_one("SELECT COUNT(*) AS count FROM picks")
        return int(row["count"] if row else 0)

    def list_picks(self, *, status: str = "", date: str = "") -> list[dict[str, Any]]:
        rows = self.db.fetch_all("SELECT * FROM picks ORDER BY created_at DESC, id DESC")
        payloads = [_row_to_payload(row) for row in rows]
        if status:
            payloads = [payload for payload in payloads if str(payload.get("status") or "").lower() == status.lower()]
        if date:
            payloads = [payload for payload in payloads if str(payload.get("date") or "") == date]
        return payloads

    def get_pick(self, pick_id: str) -> dict[str, Any] | None:
        row = self.db.fetch_one("SELECT * FROM picks WHERE id = ?", (pick_id,))
        return _row_to_payload(row) if row else None

    def upsert_pick(self, payload: dict[str, Any]) -> None:
        values = _payload_to_values(payload)
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO picks(
                  id,
                  created_at,
                  updated_at,
                  game_id,
                  player_id,
                  player_name,
                  team,
                  opponent,
                  market,
                  line,
                  side,
                  odds,
                  model_probability,
                  implied_probability,
                  edge,
                  stake_units,
                  stake_amount,
                  status,
                  source,
                  metadata_json
                ) VALUES (
                  :id,
                  :created_at,
                  :updated_at,
                  :game_id,
                  :player_id,
                  :player_name,
                  :team,
                  :opponent,
                  :market,
                  :line,
                  :side,
                  :odds,
                  :model_probability,
                  :implied_probability,
                  :edge,
                  :stake_units,
                  :stake_amount,
                  :status,
                  :source,
                  :metadata_json
                )
                ON CONFLICT(id) DO UPDATE SET
                  updated_at = excluded.updated_at,
                  game_id = excluded.game_id,
                  player_id = excluded.player_id,
                  player_name = excluded.player_name,
                  team = excluded.team,
                  opponent = excluded.opponent,
                  market = excluded.market,
                  line = excluded.line,
                  side = excluded.side,
                  odds = excluded.odds,
                  model_probability = excluded.model_probability,
                  implied_probability = excluded.implied_probability,
                  edge = excluded.edge,
                  stake_units = excluded.stake_units,
                  stake_amount = excluded.stake_amount,
                  status = excluded.status,
                  source = excluded.source,
                  metadata_json = excluded.metadata_json
                """,
                values,
            )

    def update_pick(self, pick_id: str, mutator: PickMutator) -> dict[str, Any]:
        with self.db.transaction() as connection:
            row = connection.execute("SELECT * FROM picks WHERE id = ?", (pick_id,)).fetchone()
            if row is None:
                raise PickNotFoundError(pick_id)
            updated = mutator(_row_to_payload(dict(row)))
            values = _payload_to_values(updated)
            connection.execute(
                """
                UPDATE picks SET
                  updated_at = :updated_at,
                  game_id = :game_id,
                  player_id = :player_id,
                  player_name = :player_name,
                  team = :team,
                  opponent = :opponent,
                  market = :market,
                  line = :line,
                  side = :side,
                  odds = :odds,
                  model_probability = :model_probability,
                  implied_probability = :implied_probability,
                  edge = :edge,
                  stake_units = :stake_units,
                  stake_amount = :stake_amount,
                  status = :status,
                  source = :source,
                  metadata_json = :metadata_json
                WHERE id = :id
                """,
                values,
            )
            return updated

    def replace_all(self, payloads: list[dict[str, Any]]) -> None:
        with self.db.transaction() as connection:
            connection.execute("DELETE FROM picks")
            for payload in payloads:
                connection.execute(
                    """
                    INSERT INTO picks(
                      id, created_at, updated_at, game_id, player_id, player_name,
                      team, opponent, market, line, side, odds, model_probability,
                      implied_probability, edge, stake_units, stake_amount, status,
                      source, metadata_json
                    ) VALUES (
                      :id, :created_at, :updated_at, :game_id, :player_id,
                      :player_name, :team, :opponent, :market, :line, :side,
                      :odds, :model_probability, :implied_probability, :edge,
                      :stake_units, :stake_amount, :status, :source,
                      :metadata_json
                    )
                    """,
                    _payload_to_values(payload),
                )


def _row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        metadata = json.loads(str(row.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    payload = metadata if isinstance(metadata, dict) else {}
    payload.setdefault("id", row.get("id") or "")
    payload.setdefault("createdAt", row.get("created_at") or "")
    payload.setdefault("updatedAt", row.get("updated_at") or "")
    payload.setdefault("status", row.get("status") or "Watching")
    payload.setdefault("source", row.get("source") or "edge_board")
    payload.setdefault("player", row.get("player_name") or "")
    payload.setdefault("team", row.get("team") or "")
    payload.setdefault("opponent", row.get("opponent") or "")
    payload.setdefault("market", row.get("market") or "")
    payload.setdefault("side", row.get("side") or "Over")
    if row.get("line") is not None:
        payload.setdefault("line", _display_number(row.get("line")))
    if row.get("odds") is not None:
        payload.setdefault("americanOdds", str(row.get("odds")))
    payload.setdefault("stakeUnits", float(row.get("stake_units") or 0.0))
    payload.setdefault("stakeAmount", float(row.get("stake_amount") or 0.0))
    return payload


def _payload_to_values(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(payload)
    return {
        "id": str(payload.get("id") or "").strip(),
        "created_at": str(payload.get("createdAt") or payload.get("created_at") or ""),
        "updated_at": str(payload.get("updatedAt") or payload.get("updated_at") or ""),
        "game_id": _optional_text(payload.get("gameId") or payload.get("game_id")),
        "player_id": _optional_text(payload.get("playerId") or payload.get("player_id")),
        "player_name": str(payload.get("player") or payload.get("playerName") or payload.get("player_name") or ""),
        "team": str(payload.get("team") or ""),
        "opponent": str(payload.get("opponent") or ""),
        "market": str(payload.get("market") or "unknown_market"),
        "line": _optional_float(payload.get("line")),
        "side": str(payload.get("side") or "Over"),
        "odds": _optional_int(payload.get("americanOdds") or payload.get("american_odds") or payload.get("odds")),
        "model_probability": _probability(payload.get("modelProbability") or payload.get("modelProbabilityPercent")),
        "implied_probability": _probability(payload.get("impliedProbability") or payload.get("impliedProbabilityPercent")),
        "edge": _probability(payload.get("edge") or payload.get("edgePercent")),
        "stake_units": _optional_float(payload.get("stakeUnits") or payload.get("stake_units")) or 0.0,
        "stake_amount": _optional_float(payload.get("stakeAmount") or payload.get("stake_amount")) or 0.0,
        "status": str(payload.get("status") or "Watching"),
        "source": str(payload.get("source") or "edge_board"),
        "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    }


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


def _optional_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _probability(value: Any) -> float | None:
    parsed = _optional_float(value)
    if parsed is None:
        return None
    return parsed / 100.0 if parsed > 1 else parsed


def _display_number(value: Any) -> str:
    parsed = _optional_float(value)
    if parsed is None:
        return ""
    return str(int(parsed)) if parsed.is_integer() else str(parsed)
