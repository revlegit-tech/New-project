from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.db import SQLiteDatabase, utc_now


class PredictionEventsRepository:
    """Append-only SQLite repository for prediction audit events."""

    def __init__(self, runtime_settings: Settings | None = None, *, db: SQLiteDatabase | None = None) -> None:
        self.settings = runtime_settings or default_settings
        self.db = db or SQLiteDatabase(self.settings.state_db_path)
        self.db.initialize()

    @property
    def path(self) -> Path:
        return self.db.path

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        return self._insert(event, ignore_conflicts=False)

    def append_if_absent(self, event: dict[str, Any]) -> dict[str, Any]:
        """Insert a deterministic event once and return the stored payload.

        Collector and inference wrappers may retry writes after transient failures.
        `INSERT OR IGNORE` preserves append-only semantics without duplicating the
        same event id under concurrent retry.
        """

        return self._insert(event, ignore_conflicts=True)

    def _insert(self, event: dict[str, Any], *, ignore_conflicts: bool) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("createdAt", utc_now())
        payload.setdefault("id", _event_id(payload))
        values = _payload_to_values(payload)
        conflict_clause = "OR IGNORE " if ignore_conflicts else ""
        with self.db.transaction() as connection:
            connection.execute(
                f"""
                INSERT {conflict_clause}INTO prediction_events(
                  id,
                  created_at,
                  model_key,
                  model_version,
                  market,
                  game_id,
                  player_id,
                  input_hash,
                  output_probability,
                  output_edge,
                  artifact_sha256,
                  metadata_json
                ) VALUES (
                  :id,
                  :created_at,
                  :model_key,
                  :model_version,
                  :market,
                  :game_id,
                  :player_id,
                  :input_hash,
                  :output_probability,
                  :output_edge,
                  :artifact_sha256,
                  :metadata_json
                )
                """,
                values,
            )
        existing = self.db.fetch_one("SELECT * FROM prediction_events WHERE id = ?", (values["id"],))
        return _row_to_payload(existing) if existing else payload

    def list_events(self, *, market: str = "", model_key: str = "", limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if market:
            clauses.append("market = ?")
            params.append(market)
        if model_key:
            clauses.append("model_key = ?")
            params.append(model_key)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 1000)))
        rows = self.db.fetch_all(
            f"SELECT * FROM prediction_events {where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
        return [_row_to_payload(row) for row in rows]


def _payload_to_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "created_at": str(payload.get("createdAt") or payload.get("created_at") or utc_now()),
        "model_key": str(payload.get("modelKey") or payload.get("model_key") or ""),
        "model_version": _optional_text(payload.get("modelVersion") or payload.get("model_version")),
        "market": str(payload.get("market") or ""),
        "game_id": _optional_text(payload.get("gameId") or payload.get("game_id")),
        "player_id": _optional_text(payload.get("playerId") or payload.get("player_id")),
        "input_hash": _optional_text(payload.get("inputHash") or payload.get("input_hash")),
        "output_probability": _optional_float(payload.get("outputProbability") or payload.get("output_probability")),
        "output_edge": _optional_float(payload.get("outputEdge") or payload.get("output_edge")),
        "artifact_sha256": _optional_text(payload.get("artifactSha256") or payload.get("artifact_sha256")),
        "metadata_json": json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    }


def _row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        metadata = json.loads(str(row.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    payload = metadata if isinstance(metadata, dict) else {}
    payload.setdefault("id", row.get("id") or "")
    payload.setdefault("createdAt", row.get("created_at") or "")
    payload.setdefault("modelKey", row.get("model_key") or "")
    payload.setdefault("modelVersion", row.get("model_version") or "")
    payload.setdefault("market", row.get("market") or "")
    payload.setdefault("gameId", row.get("game_id") or "")
    payload.setdefault("playerId", row.get("player_id") or "")
    payload.setdefault("inputHash", row.get("input_hash") or "")
    payload.setdefault("outputProbability", row.get("output_probability"))
    payload.setdefault("outputEdge", row.get("output_edge"))
    payload.setdefault("artifactSha256", row.get("artifact_sha256") or "")
    return payload


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_id(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
