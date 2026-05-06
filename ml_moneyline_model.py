from __future__ import annotations

"""Train and use a simple MLB team moneyline model.

Target:
    team_won

Usage:
    python ml_moneyline_model.py train data/training/moneyline_training_2026.csv
    python ml_moneyline_model.py predict --team NYY --opponent BOS --home-away home --team-moneyline -150 --opponent-moneyline 130 --game-total 8.5
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "data" / "models" / "moneyline_model.joblib"

NUMERIC_FEATURES = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
]

TEXT_FEATURES = [
    "team",
    "opponent",
    "home_away",
    "favorite_status",
]


def to_float(value: Any, default: float = 0.0) -> float:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for feature in NUMERIC_FEATURES:
        normalized[feature] = to_float(row.get(feature))

    for feature in TEXT_FEATURES:
        normalized[feature] = str(row.get(feature, "") or "").strip()

    return normalized


def load_rows(path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    rows: list[dict[str, Any]] = []
    targets: list[int] = []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            target = str(row.get("team_won", "")).strip()
            if target not in {"0", "1"}:
                continue
            rows.append(normalize_row(row))
            targets.append(int(target))

    return rows, targets


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    text_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])

    return ColumnTransformer([
        ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ("text", text_pipeline, TEXT_FEATURES),
    ])


def candidate_models() -> dict[str, Any]:
    return {
        "logistic_regression": LogisticRegression(max_iter=2000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=250,
            random_state=42,
            min_samples_leaf=3,
            class_weight="balanced",
        ),
    }


def train_model(csv_path: str | Path) -> dict[str, Any]:
    csv_path = Path(csv_path)
    rows, targets = load_rows(csv_path)

    if len(rows) < 20:
        raise ValueError(f"Need at least 20 moneyline rows. Found {len(rows)}.")

    classes = set(targets)
    if len(classes) < 2:
        raise ValueError(f"Moneyline training data needs wins and losses. Current classes: {classes}")

    y = np.array(targets)
    x = pd.DataFrame(rows)

    stratify = y if min(np.bincount(y)) >= 2 else None

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.25,
        random_state=42,
        stratify=stratify,
    )

    results: dict[str, Any] = {}
    best_name = ""
    best_score = -999.0
    best_pipeline: Pipeline | None = None

    for name, model in candidate_models().items():
        pipeline = Pipeline([
            ("preprocess", build_preprocessor()),
            ("model", model),
        ])

        pipeline.fit(x_train, y_train)
        probabilities = pipeline.predict_proba(x_test)[:, 1]

        try:
            auc = float(roc_auc_score(y_test, probabilities))
        except ValueError:
            auc = 0.5

        brier = float(brier_score_loss(y_test, probabilities))
        score = auc - brier

        results[name] = {
            "auc": auc,
            "brier": brier,
            "score": score,
        }

        if score > best_score:
            best_score = score
            best_name = name
            best_pipeline = pipeline

    if best_pipeline is None:
        raise ValueError("No model trained.")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "pipeline": best_pipeline,
        "numericFeatures": NUMERIC_FEATURES,
        "textFeatures": TEXT_FEATURES,
        "bestModel": best_name,
    }, MODEL_PATH)

    return {
        "modelPath": str(MODEL_PATH),
        "bestModel": best_name,
        "rows": len(rows),
        "classCounts": {
            "losses": int((y == 0).sum()),
            "wins": int((y == 1).sum()),
        },
        "numericFeatures": NUMERIC_FEATURES,
        "textFeatures": TEXT_FEATURES,
        "metrics": results,
    }


def predict_from_row(row: dict[str, Any]) -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Moneyline model not found: {MODEL_PATH}")

    payload = joblib.load(MODEL_PATH)
    pipeline = payload["pipeline"]
    normalized = normalize_row(row)
    probability = float(pipeline.predict_proba(pd.DataFrame([normalized]))[:, 1][0])

    return {
        "teamWinProbability": probability,
        "teamWinPercent": round(probability * 100, 2),
        "modelPath": str(MODEL_PATH),
        "bestModel": payload.get("bestModel", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train or use MLB moneyline model.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("csv")

    predict_parser = subparsers.add_parser("predict")
    predict_parser.add_argument("--team", required=True)
    predict_parser.add_argument("--opponent", required=True)
    predict_parser.add_argument("--home-away", default="home", choices=["home", "away"])
    predict_parser.add_argument("--team-moneyline", default="0")
    predict_parser.add_argument("--opponent-moneyline", default="0")
    predict_parser.add_argument("--game-total", default="0")
    predict_parser.add_argument("--favorite-status", default="")
    predict_parser.add_argument("--moneyline-implied-probability", default="0.5")

    args = parser.parse_args()

    if args.command == "train":
        print(json.dumps(train_model(args.csv), indent=2))
        return

    if args.command == "predict":
        row = {
            "team": args.team,
            "opponent": args.opponent,
            "home_away": args.home_away,
            "team_moneyline": args.team_moneyline,
            "opponent_moneyline": args.opponent_moneyline,
            "game_total": args.game_total,
            "favorite_status": args.favorite_status,
            "moneyline_implied_probability": args.moneyline_implied_probability,
        }
        print(json.dumps(predict_from_row(row), indent=2))
        return


if __name__ == "__main__":
    main()
