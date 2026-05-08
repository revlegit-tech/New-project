"""Shared utilities for Phase 15 model quality tooling.

These helpers intentionally avoid importing the app runtime so they can run in
CI, scheduled jobs, and local PowerShell sessions.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TRAINING_DIR = DATA_DIR / "training"
MODELS_DIR = DATA_DIR / "models"
BACKTEST_DIR = MODELS_DIR / "backtests"
AUDIT_DIR = MODELS_DIR / "audits"

DEFAULT_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]

LABEL_COLUMNS = ["over", "target", "label", "hit", "result", "won", "outcome"]
DATE_COLUMNS = ["date", "gameDate", "eventDate", "slateDate", "createdDate"]
NON_FEATURE_COLUMNS = {
    "player",
    "player_name",
    "name",
    "market",
    "marketDisplay",
    "baseMarket",
    "originalMarket",
    "rawLabel",
    "team",
    "opponent",
    "pitcher",
    "book",
    "sportsbook",
    "bookmaker",
    "recommendation",
    "confidence",
    "missingData",
    "books",
    "date",
    "gameDate",
    "eventDate",
    "slateDate",
    "createdDate",
    "updatedAt",
    "trainedAt",
}


def project_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    ordered.append(key)
                    seen.add(key)
        fieldnames = ordered
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    try:
        number = float(text.replace("%", ""))
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def label_value(row: dict[str, Any]) -> int | None:
    for col in LABEL_COLUMNS:
        if col not in row:
            continue
        raw = str(row.get(col, "")).strip().lower()
        if raw == "":
            continue
        if raw in {"1", "true", "t", "yes", "y", "over", "win", "won", "hit", "success"}:
            return 1
        if raw in {"0", "false", "f", "no", "n", "under", "loss", "lost", "miss", "fail", "failed"}:
            return 0
        num = coerce_float(raw)
        if num is not None and num in {0.0, 1.0}:
            return int(num)
    return None


def first_date_value(row: dict[str, Any]) -> str:
    for col in DATE_COLUMNS:
        value = str(row.get(col, "")).strip()
        if value:
            return value[:10]
    return ""


def model_feature_path(market: str) -> Path:
    return MODELS_DIR / f"prop_model_{market}_features.json"


def model_artifact_path(market: str) -> Path:
    return MODELS_DIR / f"prop_model_{market}.joblib"


def base_training_path(market: str) -> Path:
    return TRAINING_DIR / f"{market}_training.csv"


def expanded_training_path(market: str) -> Path:
    return TRAINING_DIR / f"{market}_training_expanded.csv"


def quality_training_path(market: str) -> Path:
    return TRAINING_DIR / f"{market}_training_quality.csv"


def phase15_backtest_path(market: str) -> Path:
    return BACKTEST_DIR / f"{market}_phase15_walk_forward.json"


def phase15_calibration_path(market: str) -> Path:
    return BACKTEST_DIR / f"{market}_phase15_calibration.json"


def playerboard_path(season: int) -> Path:
    return DATA_DIR / "playerboard" / f"playerboard_{season}.csv"


def load_registry() -> dict[str, Any]:
    return read_json(MODELS_DIR / "model_registry.json", default={}) or {}


def save_registry(registry: dict[str, Any]) -> None:
    atomic_write_json(MODELS_DIR / "model_registry.json", registry)


def registry_markets(registry: dict[str, Any]) -> dict[str, Any]:
    markets = registry.get("markets")
    if isinstance(markets, dict):
        return markets
    return registry


def metadata_features(market: str) -> list[str]:
    payload = read_json(model_feature_path(market), default={}) or {}
    candidates = payload.get("features") or payload.get("feature_names") or payload.get("columns") or []
    if isinstance(candidates, list):
        return [str(item) for item in candidates if str(item).strip()]
    return []


def numeric_feature_columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    cols: list[str] = []
    for col in rows[0].keys():
        if col in NON_FEATURE_COLUMNS or col in LABEL_COLUMNS:
            continue
        values = [coerce_float(row.get(col)) for row in rows[:200]]
        valid = [value for value in values if value is not None]
        if valid:
            cols.append(col)
    return cols


def feature_columns_for_market(market: str, rows: list[dict[str, Any]]) -> list[str]:
    from_metadata = metadata_features(market)
    if from_metadata:
        return from_metadata
    return numeric_feature_columns(rows)


def class_counts(rows: Iterable[dict[str, Any]]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for row in rows:
        value = label_value(row)
        if value is not None:
            counts[value] += 1
    return counts


def summarize_training_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = class_counts(rows)
    labeled = counts[0] + counts[1]
    return {
        "rows": len(rows),
        "labeledRows": labeled,
        "unlabeledRows": max(0, len(rows) - labeled),
        "classCounts": {str(k): v for k, v in sorted(counts.items())},
        "positiveRows": counts[1],
        "negativeRows": counts[0],
        "twoClass": counts[0] > 0 and counts[1] > 0,
    }


def dedupe_key(row: dict[str, Any], market: str) -> tuple[str, ...]:
    return (
        first_date_value(row),
        str(row.get("player") or row.get("player_name") or row.get("name") or "").strip().lower(),
        str(row.get("market") or row.get("baseMarket") or market).strip().lower(),
        str(row.get("line") or row.get("propLine") or "").strip(),
        str(row.get("rawLabel") or row.get("side") or row.get("label") or "").strip().lower(),
    )


def market_rows_from_playerboard(market: str, season: int, date: str | None = None) -> list[dict[str, str]]:
    rows = read_csv_rows(playerboard_path(season))
    out: list[dict[str, str]] = []
    for row in rows:
        row_market = str(row.get("market") or row.get("baseMarket") or row.get("originalMarket") or "").strip()
        if row_market != market:
            continue
        if date and first_date_value(row) and first_date_value(row) != date:
            continue
        out.append(row)
    return out


def feature_coverage(rows: list[dict[str, Any]], features: list[str]) -> dict[str, Any]:
    if not features:
        return {"featureCount": 0, "rowCount": len(rows), "averageCoverage": 0.0, "features": []}
    details = []
    total = 0.0
    for feature in features:
        present = 0
        numeric = 0
        for row in rows:
            if feature in row and str(row.get(feature, "")).strip() != "":
                present += 1
                if coerce_float(row.get(feature)) is not None:
                    numeric += 1
        denominator = max(1, len(rows))
        coverage = present / denominator
        numeric_coverage = numeric / denominator
        total += numeric_coverage
        details.append(
            {
                "feature": feature,
                "presentRows": present,
                "numericRows": numeric,
                "coverage": round(coverage, 4),
                "numericCoverage": round(numeric_coverage, 4),
            }
        )
    return {
        "featureCount": len(features),
        "rowCount": len(rows),
        "averageCoverage": round(total / max(1, len(features)), 4),
        "features": details,
    }


def production_gate_status(entry: dict[str, Any], minimum_rows: int = 100, max_brier: float = 0.25, max_log_loss: float = 0.75) -> dict[str, Any]:
    backtest = entry.get("backtest") or {}
    graded = int(coerce_float(backtest.get("graded")) or 0)
    brier = coerce_float(backtest.get("brierScore"))
    log_loss = coerce_float(backtest.get("logLoss"))
    gates = {
        "artifact": bool(entry.get("artifact")),
        "features": bool(entry.get("features")),
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
