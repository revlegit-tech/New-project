from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
ML_DIR = ROOT / "data" / "ml"
MODEL_DIR = ROOT / "models" / "team_game_markets"

DEFAULT_FEATURES = [
    "line",
    "americanOdds",
    "sportsbookImpliedProbability",
    "isHomeTeam",
    "isAwayTeam",
    "isOver",
    "isUnder",
    "isMoneyline",
    "isSpread",
    "isTotal",
    "isTeamTotal",
    "isFirstScore",
]

MIN_ROWS_PER_MARKET = 250


def clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def safe_auc(y_true, y_prob) -> float | None:
    try:
        if len(set(y_true)) < 2:
            return None
        return float(roc_auc_score(y_true, y_prob))
    except Exception:
        return None


def safe_log_loss(y_true, y_prob) -> float | None:
    try:
        return float(log_loss(y_true, y_prob, labels=[0, 1]))
    except Exception:
        return None


def evaluate(y_true, y_prob) -> dict[str, Any]:
    y_pred = (y_prob >= 0.5).astype(int)

    return {
        "rows": int(len(y_true)),
        "positiveRate": float(pd.Series(y_true).mean()) if len(y_true) else 0.0,
        "accuracy": float(accuracy_score(y_true, y_pred)) if len(y_true) else None,
        "auc": safe_auc(y_true, y_prob),
        "brier": float(brier_score_loss(y_true, y_prob)) if len(y_true) else None,
        "logLoss": safe_log_loss(y_true, y_prob),
    }


def make_models(random_state: int) -> dict[str, Pipeline]:
    return {
        "logistic": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]),
        "forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestClassifier(
                n_estimators=250,
                min_samples_leaf=20,
                random_state=random_state,
                class_weight="balanced_subsample",
                n_jobs=-1,
            )),
        ]),
        "hist_gb": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingClassifier(
                max_iter=250,
                learning_rate=0.04,
                max_leaf_nodes=15,
                min_samples_leaf=40,
                l2_regularization=0.05,
                random_state=random_state,
            )),
        ]),
    }


def predict_proba_positive(model: Pipeline, frame: pd.DataFrame) -> Any:
    proba = model.predict_proba(frame)
    if proba.shape[1] == 1:
        # Degenerate fallback.
        return proba[:, 0]
    return proba[:, 1]


def train_market(
    df: pd.DataFrame,
    market: str,
    features: list[str],
    random_state: int,
    test_size: float,
) -> dict[str, Any]:
    market_df = df[df["market"].astype(str).eq(market)].copy()

    market_df = market_df.dropna(subset=["label"])
    market_df["label"] = market_df["label"].astype(int)

    class_counts = market_df["label"].value_counts().to_dict()

    result: dict[str, Any] = {
        "market": market,
        "rows": int(len(market_df)),
        "classCounts": {str(k): int(v) for k, v in class_counts.items()},
        "features": features,
        "trained": False,
        "reason": "",
        "models": {},
        "bestModel": "",
        "bestMetric": None,
        "modelPath": "",
    }

    if len(market_df) < MIN_ROWS_PER_MARKET:
        result["reason"] = f"not enough rows; need at least {MIN_ROWS_PER_MARKET}"
        return result

    if len(class_counts) < 2:
        result["reason"] = "only one label class present"
        return result

    available_features = [col for col in features if col in market_df.columns]
    if not available_features:
        result["reason"] = "no available feature columns"
        return result

    X = market_df[available_features].apply(pd.to_numeric, errors="coerce")
    y = market_df["label"].astype(int)

    stratify = y if y.value_counts().min() >= 2 else None

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=stratify,
    )

    best_name = ""
    best_model: Pipeline | None = None
    best_score = -1.0

    for name, model in make_models(random_state).items():
        model.fit(X_train, y_train)
        train_prob = predict_proba_positive(model, X_train)
        test_prob = predict_proba_positive(model, X_test)

        train_metrics = evaluate(y_train, train_prob)
        test_metrics = evaluate(y_test, test_prob)

        # Prefer AUC when available; otherwise lower Brier.
        auc = test_metrics.get("auc")
        brier = test_metrics.get("brier")
        selection_score = float(auc) if auc is not None else (1.0 - float(brier or 1.0))

        result["models"][name] = {
            "train": train_metrics,
            "test": test_metrics,
            "selectionScore": selection_score,
        }

        if selection_score > best_score:
            best_score = selection_score
            best_name = name
            best_model = model

    if best_model is None:
        result["reason"] = "model training failed"
        return result

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"{market}_2026.joblib"

    payload = {
        "market": market,
        "features": available_features,
        "modelName": best_name,
        "trainedAt": datetime.now(timezone.utc).isoformat(),
        "model": best_model,
    }

    joblib.dump(payload, model_path)

    result["trained"] = True
    result["reason"] = "ok"
    result["features"] = available_features
    result["bestModel"] = best_name
    result["bestMetric"] = best_score
    result["modelPath"] = str(model_path)

    return result


def train_all(
    input_path: Path,
    summary_path: Path,
    random_state: int,
    test_size: float,
) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(f"Missing training file: {input_path}")

    df = pd.read_csv(input_path, low_memory=False)

    required = {"market", "label"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Training file missing required columns: {missing}")

    for col in DEFAULT_FEATURES:
        if col not in df.columns:
            df[col] = 0.0

    markets = sorted(df["market"].astype(str).dropna().unique())

    market_results = []
    for market in markets:
        print(f"Training market: {market}")
        market_results.append(
            train_market(
                df=df,
                market=market,
                features=DEFAULT_FEATURES,
                random_state=random_state,
                test_size=test_size,
            )
        )

    summary = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "modelDir": str(MODEL_DIR),
        "rows": int(len(df)),
        "markets": markets,
        "features": DEFAULT_FEATURES,
        "results": market_results,
        "trainedMarkets": [r["market"] for r in market_results if r.get("trained")],
        "skippedMarkets": [
            {"market": r["market"], "reason": r.get("reason", "")}
            for r in market_results
            if not r.get("trained")
        ],
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train baseline team/game market models.")
    parser.add_argument(
        "--input",
        default=str(ML_DIR / "team_game_markets_training_2026.csv"),
    )
    parser.add_argument(
        "--summary",
        default=str(ML_DIR / "team_game_markets_model_summary_2026.json"),
    )
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.25)
    args = parser.parse_args()

    summary = train_all(
        input_path=Path(args.input),
        summary_path=Path(args.summary),
        random_state=args.random_state,
        test_size=args.test_size,
    )

    compact = {
        "input": summary["input"],
        "modelDir": summary["modelDir"],
        "rows": summary["rows"],
        "trainedMarkets": summary["trainedMarkets"],
        "skippedMarkets": summary["skippedMarkets"],
    }

    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
