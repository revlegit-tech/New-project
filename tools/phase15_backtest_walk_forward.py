from __future__ import annotations

import argparse
import json
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase15_common import (
    DEFAULT_MARKETS,
    atomic_write_json,
    first_date_value,
    label_value,
    load_registry,
    phase15_backtest_path,
    quality_training_path,
    read_csv_rows,
    registry_markets,
    save_registry,
    feature_columns_for_market,
)


def _require_sklearn():
    try:
        import numpy as np
        from sklearn.calibration import calibration_curve
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(f"Phase 15 backtest requires scikit-learn and numpy: {exc}") from exc
    return np, SimpleImputer, LogisticRegression, make_pipeline, StandardScaler, brier_score_loss, log_loss, roc_auc_score


def _row_matrix(rows: list[dict[str, Any]], features: list[str]):
    matrix = []
    for row in rows:
        values = []
        for feature in features:
            raw = row.get(feature)
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                values.append(float("nan"))
        matrix.append(values)
    return matrix


def _split_rows(rows: list[dict[str, Any]], holdout_fraction: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    rows = [row for row in rows if label_value(row) is not None]
    dated = [row for row in rows if first_date_value(row)]
    if len(dated) >= max(20, int(len(rows) * 0.6)):
        rows = sorted(rows, key=lambda row: first_date_value(row))
        source = "walk_forward_date"
    else:
        source = "row_order_holdout"
    split = max(1, int(len(rows) * (1 - holdout_fraction)))
    split = min(split, len(rows) - 1)
    return rows[:split], rows[split:], source


def backtest_market(market: str, holdout_fraction: float = 0.25) -> dict[str, Any]:
    np, SimpleImputer, LogisticRegression, make_pipeline, StandardScaler, brier_score_loss, log_loss, roc_auc_score = _require_sklearn()
    rows = read_csv_rows(quality_training_path(market))
    if not rows:
        return {"market": market, "status": "missing_quality_dataset", "trainingPath": str(quality_training_path(market))}
    train_rows, test_rows, source = _split_rows(rows, holdout_fraction)
    features = feature_columns_for_market(market, rows)
    if not features:
        return {"market": market, "status": "missing_features", "trainingPath": str(quality_training_path(market))}
    y_train = [label_value(row) for row in train_rows]
    y_test = [label_value(row) for row in test_rows]
    if len(set(y_train)) < 2 or len(set(y_test)) < 2:
        return {
            "market": market,
            "status": "insufficient_classes_for_holdout",
            "trainingRows": len(train_rows),
            "graded": len(test_rows),
            "trainClasses": sorted(set(v for v in y_train if v is not None)),
            "testClasses": sorted(set(v for v in y_test if v is not None)),
            "source": source,
        }
    x_train = np.array(_row_matrix(train_rows, features), dtype=float)
    x_test = np.array(_row_matrix(test_rows, features), dtype=float)
    y_train_arr = np.array(y_train, dtype=int)
    y_test_arr = np.array(y_test, dtype=int)

    model = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )
    model.fit(x_train, y_train_arr)
    probs = model.predict_proba(x_test)[:, 1]
    eps = 1e-15
    clipped = np.clip(probs, eps, 1 - eps)
    try:
        auc = float(roc_auc_score(y_test_arr, probs))
    except ValueError:
        auc = None
    predictions = []
    for row, truth, prob in zip(test_rows, y_test_arr.tolist(), probs.tolist()):
        predictions.append(
            {
                "date": first_date_value(row),
                "player": row.get("player") or row.get("player_name") or row.get("name") or "",
                "market": market,
                "line": row.get("line") or row.get("propLine") or "",
                "actual": int(truth),
                "probability": round(float(prob), 6),
            }
        )
    return {
        "market": market,
        "status": "ok",
        "source": source,
        "trainingPath": str(quality_training_path(market)),
        "featureCount": len(features),
        "features": features,
        "trainingRows": len(train_rows),
        "totalRows": len(rows),
        "graded": len(test_rows),
        "brierScore": round(float(brier_score_loss(y_test_arr, clipped)), 6),
        "logLoss": round(float(log_loss(y_test_arr, clipped, labels=[0, 1])), 6),
        "auc": None if auc is None else round(auc, 6),
        "predictions": predictions,
        "out": str(phase15_backtest_path(market)),
    }


def run(markets: list[str], update_registry: bool = False, holdout_fraction: float = 0.25) -> dict[str, Any]:
    results = [backtest_market(market, holdout_fraction=holdout_fraction) for market in markets]
    for result in results:
        if result.get("status") == "ok":
            out = phase15_backtest_path(result["market"])
            atomic_write_json(out, result)
    if update_registry:
        registry = load_registry()
        markets_map = registry_markets(registry)
        for result in results:
            if result.get("status") != "ok":
                continue
            entry = markets_map.setdefault(result["market"], {})
            previous_status = entry.get("status") or "experimental"
            entry["status"] = previous_status if previous_status == "production" else "experimental"
            entry["backtest"] = {
                "graded": result["graded"],
                "brierScore": result["brierScore"],
                "logLoss": result["logLoss"],
                "auc": result.get("auc"),
                "source": result["source"],
            }
        save_registry(registry)
    public_results = []
    for result in results:
        result = dict(result)
        if "predictions" in result:
            result["predictionRows"] = len(result["predictions"])
            del result["predictions"]
        public_results.append(result)
    return {"status": "ok", "updatedRegistry": update_registry, "results": public_results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 15 walk-forward model backtests.")
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    parser.add_argument("--holdout-fraction", type=float, default=0.25)
    parser.add_argument("--update-registry", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.markets, update_registry=args.update_registry, holdout_fraction=args.holdout_fraction), indent=2))


if __name__ == "__main__":
    main()
