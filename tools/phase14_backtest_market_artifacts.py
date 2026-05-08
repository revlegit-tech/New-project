from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORTS))

from tools.phase14_common import (
    BACKTEST_DIR,
    DEFAULT_MARKETS,
    as_float,
    infer_binary_target,
    load_registry,
    market_training_path,
    model_artifact_path,
    model_features_path,
    read_csv_rows,
    registry_markets,
    save_registry,
    write_json_atomic,
)


def load_features(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(item) for item in payload]
    if isinstance(payload, dict):
        for key in ["features", "feature_names", "columns"]:
            if isinstance(payload.get(key), list):
                return [str(item) for item in payload[key]]
    return []


def load_model(path: Path) -> Any:
    try:
        import joblib  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("joblib is required to load market model artifacts") from exc
    return joblib.load(path)


def predict_probabilities(model: Any, rows: list[dict[str, Any]], features: list[str]) -> list[float]:
    matrix: list[list[float]] = []
    for row in rows:
        matrix.append([as_float(row.get(feature)) or 0.0 for feature in features])
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(matrix)
        return [float(row[1]) for row in probabilities]
    if hasattr(model, "decision_function"):
        import math

        scores = model.decision_function(matrix)
        return [1.0 / (1.0 + math.exp(-float(score))) for score in scores]
    predictions = model.predict(matrix)
    return [float(value) for value in predictions]


def metric_summary(labels: list[int], probs: list[float]) -> dict[str, Any]:
    import math

    eps = 1e-9
    n = len(labels)
    if n == 0:
        return {"graded": 0, "brierScore": None, "logLoss": None, "auc": None}
    brier = sum((p - y) ** 2 for y, p in zip(labels, probs)) / n
    log_loss = -sum(y * math.log(max(min(p, 1 - eps), eps)) + (1 - y) * math.log(max(min(1 - p, 1 - eps), eps)) for y, p in zip(labels, probs)) / n
    auc = None
    if len(set(labels)) == 2:
        try:
            from sklearn.metrics import roc_auc_score  # type: ignore

            auc = float(roc_auc_score(labels, probs))
        except Exception:
            auc = None
    return {"graded": n, "brierScore": round(brier, 6), "logLoss": round(log_loss, 6), "auc": auc}


def backtest_market(market: str, *, holdout_fraction: float = 0.25) -> dict[str, Any]:
    artifact = model_artifact_path(market)
    features_path = model_features_path(market)
    training_path = market_training_path(market, expanded=True)
    if not training_path.exists():
        training_path = market_training_path(market)
    rows = read_csv_rows(training_path)
    labeled = [row for row in rows if infer_binary_target(row) is not None]
    if not artifact.exists():
        return {"market": market, "status": "skipped", "reason": "missing model artifact", "artifact": str(artifact)}
    features = load_features(features_path)
    if not features:
        return {"market": market, "status": "skipped", "reason": "missing feature metadata", "features": str(features_path)}
    if len(labeled) < 10:
        return {"market": market, "status": "skipped", "reason": "not enough labeled rows", "labeledRows": len(labeled)}
    holdout_size = max(1, int(round(len(labeled) * holdout_fraction)))
    holdout = labeled[-holdout_size:]
    labels = [int(infer_binary_target(row) or 0) for row in holdout]
    if len(set(labels)) < 2:
        return {"market": market, "status": "skipped", "reason": "holdout has only one class", "graded": len(labels)}
    model = load_model(artifact)
    probs = predict_probabilities(model, holdout, features)
    metrics = metric_summary(labels, probs)
    report = {
        "market": market,
        "status": "ok",
        "source": "phase14_holdout",
        "trainingPath": str(training_path),
        "artifact": str(artifact),
        "features": str(features_path),
        "featureCount": len(features),
        "trainingRows": len(rows),
        **metrics,
    }
    return report


def update_registry_with_report(market: str, report: dict[str, Any]) -> None:
    registry = load_registry()
    markets = registry_markets(registry)
    entry = markets.setdefault(market, {})
    existing = entry.get("backtest") or {}
    if report.get("status") == "ok":
        # Keep the larger graded sample if one already exists.
        if int(report.get("graded") or 0) >= int(existing.get("graded") or existing.get("rows") or 0):
            entry["backtest"] = {
                "graded": report.get("graded"),
                "brierScore": report.get("brierScore"),
                "logLoss": report.get("logLoss"),
                "auc": report.get("auc"),
                "source": report.get("source"),
            }
        entry.setdefault("status", "experimental")
    save_registry(registry)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest exact market model artifacts on held-out labeled rows.")
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--holdout-fraction", type=float, default=0.25)
    parser.add_argument("--update-registry", action="store_true")
    args = parser.parse_args()
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for market in args.markets:
        report = backtest_market(market, holdout_fraction=args.holdout_fraction)
        out = BACKTEST_DIR / f"{market}_phase14_backtest.json"
        write_json_atomic(out, report)
        report["out"] = str(out)
        if args.update_registry:
            update_registry_with_report(market, report)
        results.append(report)
    print(json.dumps({"status": "ok", "updatedRegistry": args.update_registry, "results": results}, indent=2))


if __name__ == "__main__":
    main()
