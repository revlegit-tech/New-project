from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
    "team_first_score",
]
MODEL_DIR = ROOT / "data" / "models"
TRAINING_DIR = ROOT / "data" / "training"
PLAYERBOARD_DIR = ROOT / "data" / "playerboard"
PREDICTIONS_DIR = ROOT / "data" / "predictions"
BACKTEST_DIR = MODEL_DIR / "backtests"
REGISTRY_PATH = MODEL_DIR / "model_registry.json"

TARGET_FIELDS = [
    "over",
    "is_over",
    "actual_over",
    "went_over",
    "target",
    "label",
    "is_hit",
    "hit",
    "won",
    "win",
    "graded_win",
    "result_binary",
    "outcome_binary",
]
RESULT_FIELDS = ["result", "grade", "outcome", "status", "pick_result"]
MARKET_FIELDS = ["market", "baseMarket", "base_market", "market_key", "prop_market"]
PLAYER_FIELDS = ["player", "player_name", "name"]
DATE_FIELDS = ["date", "gameDate", "game_date", "slateDate", "slate_date"]

NUMERIC_FEATURE_CANDIDATES = [
    "line",
    "americanOdds",
    "american_odds",
    "finalProbabilityPercent",
    "final_probability_percent",
    "sportsbookImpliedPercent",
    "sportsbook_implied_percent",
    "finalEdgePercent",
    "final_edge_percent",
    "weatherAdjustmentPercent",
    "savantAdjustmentPercent",
    "oddsMovementAdjustmentPercent",
    "l5HitRate",
    "l10HitRate",
    "l20HitRate",
    "h2hHitRate",
    "seasonHitRate",
    "previousSeasonHitRate",
]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        seen: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.append(key)
        fieldnames = seen
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def first_present(row: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return ""


def normalize_market(value: Any) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    value = value.replace("-", "_").replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9_]+", "", value)
    return value.lower()


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def infer_binary_target(row: dict[str, Any]) -> int | None:
    for field in TARGET_FIELDS:
        if field not in row:
            continue
        raw = row.get(field)
        if raw is None or str(raw).strip() == "":
            continue
        text = str(raw).strip().lower()
        if text in {"1", "true", "t", "yes", "y", "win", "won", "hit", "over", "success"}:
            return 1
        if text in {"0", "false", "f", "no", "n", "loss", "lost", "miss", "under", "fail", "push"}:
            return 0
        numeric = as_float(raw)
        if numeric is not None:
            # Match the Phase 13 trainer: binary target columns often store
            # 0/1, but some exported rows use numeric truthy values.
            return 1 if numeric >= 1.0 else 0
    for field in RESULT_FIELDS:
        if field not in row:
            continue
        text = str(row.get(field) or "").strip().lower()
        if not text:
            continue
        if text in {"win", "won", "hit", "correct", "cash", "success"}:
            return 1
        if text in {"loss", "lost", "miss", "incorrect", "fail", "failed"}:
            return 0
        if text == "push":
            return 0
    return None


def market_training_path(market: str, expanded: bool = False) -> Path:
    suffix = "_training_expanded.csv" if expanded else "_training.csv"
    return TRAINING_DIR / f"{market}{suffix}"


def model_artifact_path(market: str) -> Path:
    return MODEL_DIR / f"prop_model_{market}.joblib"


def model_features_path(market: str) -> Path:
    return MODEL_DIR / f"prop_model_{market}_features.json"


def stable_row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(first_present(row, DATE_FIELDS)),
        str(first_present(row, PLAYER_FIELDS)).strip().lower(),
        normalize_market(first_present(row, MARKET_FIELDS)),
        str(row.get("line", "")),
        str(row.get("rawLabel") or row.get("side") or row.get("pick") or "").lower(),
    )


def summarize_training_file(path: Path) -> dict[str, Any]:
    rows = read_csv_rows(path)
    targets: list[int] = []
    unlabeled = 0
    for row in rows:
        label = infer_binary_target(row)
        if label is None:
            unlabeled += 1
        else:
            targets.append(label)
    counts = Counter(str(value) for value in targets)
    return {
        "path": str(path),
        "exists": path.exists(),
        "rows": len(rows),
        "labeledRows": len(targets),
        "unlabeledRows": unlabeled,
        "classCounts": dict(counts),
        "positiveRows": counts.get("1", 0),
        "negativeRows": counts.get("0", 0),
        "twoClass": counts.get("1", 0) > 0 and counts.get("0", 0) > 0,
    }


def load_registry() -> dict[str, Any]:
    payload = read_json(REGISTRY_PATH, default={})
    return payload if isinstance(payload, dict) else {}


def registry_markets(registry: dict[str, Any]) -> dict[str, Any]:
    if "markets" in registry and isinstance(registry["markets"], dict):
        return registry["markets"]
    return registry


def save_registry(registry: dict[str, Any]) -> None:
    write_json_atomic(REGISTRY_PATH, registry)


def production_gate_status(entry: dict[str, Any], *, minimum_rows: int = 100, max_brier: float = 0.25, max_log_loss: float = 0.75) -> dict[str, Any]:
    backtest = entry.get("backtest") or {}
    graded = int(backtest.get("graded") or backtest.get("rows") or 0)
    brier = as_float(backtest.get("brierScore") if "brierScore" in backtest else backtest.get("brier_score"))
    log_loss = as_float(backtest.get("logLoss") if "logLoss" in backtest else backtest.get("log_loss"))
    artifact = entry.get("artifact") or entry.get("modelPath") or entry.get("model_path")
    features = entry.get("features") or entry.get("metadata") or entry.get("featureMetadata")
    gates = {
        "artifact": bool(artifact),
        "features": bool(features),
        "calibrated": bool(entry.get("calibrated")),
        "minimumBacktestRows": graded >= minimum_rows,
        "brier": brier is not None and brier <= max_brier,
        "logLoss": log_loss is not None and log_loss <= max_log_loss,
    }
    return {
        "ok": all(gates.values()),
        "gates": gates,
        "graded": graded,
        "brierScore": brier,
        "logLoss": log_loss,
        "minimumRows": minimum_rows,
        "maxBrierScore": max_brier,
        "maxLogLoss": max_log_loss,
        "missing": [name for name, ok in gates.items() if not ok],
    }
