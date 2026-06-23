from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from mlb_app.ml.datasets.leakage_guard import assert_training_row_contract


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _prop_key(row: dict[str, Any], *, prefix: str) -> tuple[str, ...]:
    return (
        _clean(row.get(f"{prefix}source") or row.get("source") or "actionnetwork"),
        _clean(row.get(f"{prefix}game_date") or row.get("game_date")),
        _clean(row.get(f"{prefix}event_id") or row.get("event_id")),
        _clean(row.get(f"{prefix}player_id") or row.get("player_id") or row.get(f"{prefix}team_id") or row.get("team_id")),
        _clean(row.get(f"{prefix}market_group") or row.get("market_group")),
        _clean(row.get(f"{prefix}market_type") or row.get("market_type")),
        _clean(row.get(f"{prefix}line") or row.get("line")),
        _clean(row.get(f"{prefix}bet_side") or row.get("bet_side")),
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ActionNetworkTrainingDatasetService:
    def build_rows(
        self,
        *,
        labels: list[dict[str, str]],
        movement_features: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        features_by_key = {_prop_key(row, prefix="meta_"): row for row in movement_features}
        rows: list[dict[str, Any]] = []
        skipped: dict[str, int] = {}

        for label in labels:
            reason = self._skip_reason(label)
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue

            feature = features_by_key.get(_prop_key(label, prefix=""))
            if not feature:
                skipped["missing_features"] = skipped.get("missing_features", 0) + 1
                continue

            row: dict[str, Any] = {}
            for key, value in feature.items():
                if key.startswith(("feature_", "meta_")):
                    row[key] = value

            row.update(
                {
                    "meta_gamePk": label.get("gamePk", ""),
                    "meta_snapshot_id": label.get("snapshot_id", ""),
                    "meta_collection_mode": label.get("collection_mode", ""),
                    "meta_bridge_status": label.get("bridge_status", ""),
                    "target_actual_stat": label.get("actual_stat", ""),
                    "target_result": label.get("label_result", ""),
                    "target_hit": "1" if label.get("label_result") == "win" else "0",
                    "target_push": "0",
                    "target_exclude_from_ml": label.get("exclude_from_ml", ""),
                }
            )
            assert_training_row_contract(row)
            rows.append(row)

        return rows, {
            "input_labels": len(labels),
            "input_features": len(movement_features),
            "trainable_rows": len(rows),
            "skipped_counts": skipped,
            "feature_columns": sorted({key for row in rows for key in row if key.startswith("feature_")}),
            "target_columns": sorted({key for row in rows for key in row if key.startswith("target_")}),
            "metadata_columns": sorted({key for row in rows for key in row if key.startswith("meta_")}),
        }

    def _skip_reason(self, label: dict[str, str]) -> str:
        if label.get("exclude_from_ml") != "0":
            return "excluded"
        if label.get("collection_mode") != "live_forward":
            return "not_live_forward"
        if label.get("bridge_status") != "confirmed":
            return "bridge_not_confirmed"
        if label.get("label_result") not in {"win", "loss"}:
            return "not_win_loss"
        if label.get("validation_status") != "valid_labeled_event_confirmed":
            return "not_event_confirmed"
        return ""


def write_dataset(csv_path: Path, summary_path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
