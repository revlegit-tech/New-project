from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.csv_store import CsvStore
from mlb_app.repositories.db import SQLiteDatabase, utc_now


SHADOW_PREDICTION_FIELDS: tuple[str, ...] = (
    "prediction_id",
    "model_name",
    "model_version",
    "model_status",
    "market",
    "game_date",
    "game_id",
    "player",
    "team",
    "opponent",
    "line",
    "side",
    "sportsbook",
    "market_probability",
    "model_probability",
    "context_probability",
    "blended_shadow_probability",
    "edge",
    "feature_coverage",
    "warnings",
    "created_at",
    "target_actual_value",
    "target_hit",
    "target_push",
    "target_result",
    "target_profit_1u",
    "evaluated_at",
)


class ShadowPredictionRepository:
    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        db: SQLiteDatabase | None = None,
        csv_store: CsvStore | None = None,
        csv_path: str | Path | None = None,
    ) -> None:
        self.settings = settings
        self.db = db or SQLiteDatabase(settings.state_db_path)
        self.csv_store = csv_store or CsvStore()
        self.csv_path = Path(csv_path or settings.data_dir / "predictions" / "shadow_predictions.csv")
        if settings.db_enabled:
            self.db.initialize()
            self._ensure_table()

    def append_many(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        clean_rows = [_normalize_row(row) for row in rows]
        if self.settings.db_enabled:
            self._insert_db(clean_rows)
            return {"backend": "sqlite", "path": _public_path(self.settings.root_dir, self.settings.state_db_path), "rowCount": len(clean_rows)}
        existing = self.csv_store.read_rows_uncached(self.csv_path)
        self.csv_store.write_rows(self.csv_path, [*existing, *clean_rows], list(SHADOW_PREDICTION_FIELDS))
        return {"backend": "csv", "path": _public_path(self.settings.root_dir, self.csv_path), "rowCount": len(clean_rows)}

    def list_predictions(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        if self.settings.db_enabled:
            self._ensure_table()
            rows = self.db.fetch_all(
                "SELECT payload_json FROM shadow_predictions ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 10000)),),
            )
            out: list[dict[str, Any]] = []
            for row in rows:
                try:
                    payload = json.loads(str(row.get("payload_json") or "{}"))
                except json.JSONDecodeError:
                    payload = {}
                if isinstance(payload, dict):
                    out.append(payload)
            return out
        return [dict(row) for row in self.csv_store.read_rows_uncached(self.csv_path)[: max(1, min(int(limit), 10000))]]

    def mark_evaluated(self, prediction_id: str, targets: dict[str, Any]) -> dict[str, Any]:
        rows = self.list_predictions(limit=10000)
        updated = 0
        evaluated_at = utc_now()
        for row in rows:
            if str(row.get("prediction_id") or "") != prediction_id:
                continue
            for key in ("target_actual_value", "target_hit", "target_push", "target_result", "target_profit_1u"):
                if key in targets:
                    row[key] = targets[key]
            row["evaluated_at"] = evaluated_at
            updated += 1
        if self.settings.db_enabled:
            self._replace_db(rows)
        else:
            self.csv_store.write_rows(self.csv_path, rows, list(SHADOW_PREDICTION_FIELDS))
        return {"updated": updated, "evaluatedAt": evaluated_at}

    def _ensure_table(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_predictions (
              prediction_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              market TEXT NOT NULL,
              model_name TEXT,
              model_version TEXT,
              model_status TEXT,
              payload_json TEXT NOT NULL
            )
            """
        )

    def _insert_db(self, rows: list[dict[str, Any]]) -> None:
        self._ensure_table()
        with self.db.transaction() as connection:
            for row in rows:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO shadow_predictions(
                      prediction_id, created_at, market, model_name, model_version, model_status, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["prediction_id"],
                        row["created_at"],
                        row["market"],
                        row["model_name"],
                        row["model_version"],
                        row["model_status"],
                        json.dumps(row, sort_keys=True, default=str, separators=(",", ":")),
                    ),
                )

    def _replace_db(self, rows: list[dict[str, Any]]) -> None:
        self._ensure_table()
        with self.db.transaction() as connection:
            connection.execute("DELETE FROM shadow_predictions")
            for row in rows:
                normalized = _normalize_row(row)
                connection.execute(
                    """
                    INSERT OR REPLACE INTO shadow_predictions(
                      prediction_id, created_at, market, model_name, model_version, model_status, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["prediction_id"],
                        normalized["created_at"],
                        normalized["market"],
                        normalized["model_name"],
                        normalized["model_version"],
                        normalized["model_status"],
                        json.dumps(normalized, sort_keys=True, default=str, separators=(",", ":")),
                    ),
                )


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {field: row.get(field, "") for field in SHADOW_PREDICTION_FIELDS}
    out["warnings"] = json.dumps(row.get("warnings") or [], sort_keys=True) if not isinstance(row.get("warnings"), str) else row.get("warnings")
    out["created_at"] = str(out.get("created_at") or utc_now())
    out["prediction_id"] = str(out.get("prediction_id") or "")
    return out


def _public_path(root: Path, path: Path | str) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return Path(path).name
