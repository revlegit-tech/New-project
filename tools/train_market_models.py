#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.model_registry_service import DEFAULT_MARKETS, MIN_TRAINING_ROWS  # noqa: E402

TARGET_CANDIDATES = ("over", "target", "label", "hit", "result")
EXCLUDE_COLUMNS = {
    "date",
    "game_date",
    "player",
    "player_name",
    "team",
    "opponent",
    "market",
    "market_display",
    "marketDisplay",
    "book",
    "bookmaker",
    "sportsbook",
    "recommendation",
    "result",
    "rawLabel",
    "raw_label",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train market-specific model artifacts and update model_registry.json.")
    parser.add_argument("--markets", nargs="*", default=list(DEFAULT_MARKETS), help="Markets to train. Defaults to Phase 13 priority markets.")
    parser.add_argument("--data-dir", default=str(ROOT / "data"), help="Data directory containing training CSVs.")
    parser.add_argument("--model-dir", default=str(ROOT / "data" / "models"), help="Directory for artifacts and registry.")
    parser.add_argument("--registry", default="", help="Registry JSON path. Defaults to <model-dir>/model_registry.json.")
    parser.add_argument("--min-rows", type=int, default=MIN_TRAINING_ROWS)
    parser.add_argument("--calibrate", action="store_true", help="Wrap LogisticRegression in calibrated probabilities when each class has at least 3 rows.")
    parser.add_argument("--promote-candidates", action="store_true", help="Mark calibrated artifacts as production_candidate only when local holdout metrics are healthy.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    model_dir = Path(args.model_dir).resolve()
    registry_path = Path(args.registry).resolve() if args.registry else model_dir / "model_registry.json"
    model_dir.mkdir(parents=True, exist_ok=True)
    registry = _load_json(registry_path)

    results = []
    for market in args.markets:
        key = _market_key(market)
        result = train_market(
            key,
            data_dir=data_dir,
            model_dir=model_dir,
            min_rows=args.min_rows,
            calibrate=args.calibrate,
            promote_candidates=args.promote_candidates,
            dry_run=args.dry_run,
        )
        results.append(result)
        if result["status"] in {"trained", "dry_run"}:
            registry[key] = result["registryEntry"]
        elif key not in registry:
            registry[key] = {
                "status": "not_ready",
                "artifact": str((model_dir / f"prop_model_{key}.joblib").relative_to(ROOT)),
                "features": str((model_dir / f"prop_model_{key}_features.json").relative_to(ROOT)),
                "calibrated": False,
                "reason": result.get("reason", "not trained"),
            }

    if not args.dry_run:
        _write_json_atomic(registry_path, registry)

    print(json.dumps({"status": "ok", "dryRun": args.dry_run, "registryPath": str(registry_path), "results": results}, indent=2))


def train_market(
    market: str,
    *,
    data_dir: Path,
    model_dir: Path,
    min_rows: int,
    calibrate: bool,
    promote_candidates: bool,
    dry_run: bool,
) -> dict[str, Any]:
    training_path = data_dir / "training" / f"{market}_training.csv"
    if not training_path.exists():
        return {"market": market, "status": "skipped", "reason": f"missing training file: {training_path}"}

    df = pd.read_csv(training_path)
    if df.empty:
        return {"market": market, "status": "skipped", "reason": "training file is empty"}

    target_col = _target_column(df)
    if not target_col:
        return {"market": market, "status": "skipped", "reason": "no target column found"}

    y = _normalize_target(df[target_col])
    valid = y.notna()
    df = df.loc[valid].copy()
    y = y.loc[valid].astype(int)

    class_counts = y.value_counts().to_dict()
    positive_rows = int(class_counts.get(1, 0))
    negative_rows = int(class_counts.get(0, 0))
    if len(df) < min_rows:
        return {"market": market, "status": "skipped", "reason": f"fewer than {min_rows} rows", "trainingRows": len(df)}
    if positive_rows == 0 or negative_rows == 0:
        return {"market": market, "status": "skipped", "reason": "training data has one class only", "trainingRows": len(df), "classCounts": class_counts}

    feature_cols = _feature_columns(df, target_col)
    if not feature_cols:
        return {"market": market, "status": "skipped", "reason": "no numeric feature columns found", "trainingRows": len(df)}

    X = df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    can_split = min(positive_rows, negative_rows) >= 2 and len(df) >= 40
    if can_split:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    else:
        X_train, X_test, y_train, y_test = X, X, y, y

    base = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    calibrated = False
    model: Any = base
    if calibrate and min(positive_rows, negative_rows) >= 3:
        try:
            model = CalibratedClassifierCV(base, cv=3, method="sigmoid")
            calibrated = True
        except TypeError:
            model = CalibratedClassifierCV(base_estimator=base, cv=3, method="sigmoid")
            calibrated = True

    model.fit(X_train, y_train)
    probabilities = model.predict_proba(X_test)[:, 1]
    metrics = _metrics(y_test, probabilities)
    trained_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    artifact_path = model_dir / f"prop_model_{market}.joblib"
    features_path = model_dir / f"prop_model_{market}_features.json"

    status = "experimental"
    if promote_candidates and calibrated and len(y_test) >= 25 and metrics.get("brierScore", 1.0) <= 0.25:
        status = "production_candidate"

    registry_entry = {
        "artifact": _rel(artifact_path),
        "features": _rel(features_path),
        "status": status,
        "trained_at": trained_at,
        "training_rows": int(len(df)),
        "positive_rows": positive_rows,
        "negative_rows": negative_rows,
        "feature_count": len(feature_cols),
        "calibrated": calibrated,
        "model_type": "calibrated_logistic_regression" if calibrated else "logistic_regression",
        "backtest": {
            "graded": int(len(y_test)),
            "brierScore": metrics.get("brierScore"),
            "logLoss": metrics.get("logLoss"),
            "auc": metrics.get("auc"),
            "source": "local_holdout",
        },
    }

    metadata = {
        "schema": "market-model-metadata-v1",
        "market": market,
        "features": feature_cols,
        "target": target_col,
        "trainedAt": trained_at,
        "trainingRows": int(len(df)),
        "positiveRows": positive_rows,
        "negativeRows": negative_rows,
        "modelType": registry_entry["model_type"],
        "calibrated": calibrated,
        "metrics": metrics,
    }

    if not dry_run:
        joblib.dump(model, artifact_path)
        _write_json_atomic(features_path, metadata)

    return {
        "market": market,
        "status": "dry_run" if dry_run else "trained",
        "trainingPath": str(training_path),
        "artifact": str(artifact_path),
        "features": str(features_path),
        "trainingRows": int(len(df)),
        "positiveRows": positive_rows,
        "negativeRows": negative_rows,
        "featureCount": len(feature_cols),
        "calibrated": calibrated,
        "metrics": metrics,
        "registryEntry": registry_entry,
    }


def _target_column(df: pd.DataFrame) -> str:
    for name in TARGET_CANDIDATES:
        if name in df.columns:
            return name
    return ""


def _normalize_target(series: pd.Series) -> pd.Series:
    def one(value: Any) -> int | None:
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "over", "hit", "win", "won"}:
            return 1
        if text in {"0", "false", "no", "n", "under", "miss", "loss", "lost"}:
            return 0
        try:
            return 1 if float(text) >= 1 else 0
        except ValueError:
            return None

    return series.map(one)


def _feature_columns(df: pd.DataFrame, target_col: str) -> list[str]:
    cols: list[str] = []
    for col in df.columns:
        if col == target_col or col in EXCLUDE_COLUMNS:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() >= max(5, int(len(df) * 0.5)):
            cols.append(col)
    return cols


def _metrics(y_true: pd.Series, probability: Any) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    try:
        out["brierScore"] = round(float(brier_score_loss(y_true, probability)), 6)
    except Exception:
        out["brierScore"] = None
    try:
        out["logLoss"] = round(float(log_loss(y_true, probability, labels=[0, 1])), 6)
    except Exception:
        out["logLoss"] = None
    try:
        if len(set(y_true.tolist())) == 2:
            out["auc"] = round(float(roc_auc_score(y_true, probability)), 6)
        else:
            out["auc"] = None
    except Exception:
        out["auc"] = None
    return out


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def _market_key(value: object) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


if __name__ == "__main__":
    main()
