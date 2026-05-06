from __future__ import annotations

"""Free machine-learning helpers for Baseball Prop Predictor.

This module trains a scikit-learn model from historical prop results and
returns probability, fair odds, edge, and expected value for one prop row.
"""

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "data" / "models"
DEFAULT_MODEL_PATH = MODEL_DIR / "prop_model.joblib"
DEFAULT_FEATURES_PATH = MODEL_DIR / "prop_model_features.json"

DEFAULT_FEATURE_COLUMNS = [
    # Line / market
    "line",
    "book_implied_probability",
    "line_move",
    "odds_move",
    "vig_pct",

    # Batter recent form
    "recent_games",
    "recent_rate",
    "season_rate",
    "rolling_avg_5",
    "rolling_avg_10",
    "rolling_avg_15",
    "rolling_total_bases_10",
    "rolling_hr_rate_15",
    "rolling_k_rate_10",

    # Batter season stats
    "batter_babip",
    "batter_k_rate",
    "batter_walk_rate",
    "batter_days_rest",
    "batter_avg_home",
    "batter_avg_away",

    # Batter advanced / Savant
    "barrel_rate",
    "hard_hit_rate",
    "xwoba",
    "xba",
    "xslg",
    "batter_ld_rate",
    "batter_gb_rate",
    "batter_sprint_speed",

    # Batter platoon splits
    "batter_avg_vs_hand",
    "batter_k_rate_vs_hand",
    "batter_recent_hits_vs_lhp",
    "batter_recent_hits_vs_rhp",

    # Pitcher season stats
    "pitcher_k_rate",
    "pitcher_walk_rate",
    "pitcher_hr_rate",
    "pitcher_babip",
    "pitcher_days_rest",
    "pitcher_velo_delta",

    # Pitcher platoon splits
    "pitcher_avg_allowed_vs_hand",

    # Team context
    "team_k_rate",
    "team_walk_rate",
    "opponent_rate",
    "opponent_bullpen_era_7d",

    # Umpire
    "ump_k_rate",
    "ump_zone_size_zscore",
    "ump_favor_batter_score",

    # Park / weather
    "park_factor",
    "hit_factor",
    "hr_factor",
    "k_factor",
    "temperature",
    "wind_mph",
    "wind_out_score",
    "wind_out_flag",
    "turf_flag",
    "cold_game_flag",
]

MISSING_INDICATOR_FEATURES = [
    "pitcher_days_rest",
    "batter_avg_vs_hand",
    "ump_k_rate",
    "pitcher_velo_delta",
]
TEXT_COLUMNS = [
    "market", "player", "pitcher", "team", "opponent",
    "throws", "bats", "venue", "roof", "platoon_matchup",
]
TARGET_ALIASES = ["over", "hit", "result", "won", "actual_over", "target"]
ACTUAL_ALIASES = ["actual", "actual_stat", "result_stat", "stat", "value"]
LINE_ALIASES = ["line", "sportsbook_line", "prop_line"]
ODDS_ALIASES = ["american_odds", "odds", "price", "over_odds", "overOdds"]
UNDER_ODDS_ALIASES = ["under_odds", "underOdds", "under_price", "underPrice"]


def normalize_key(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def model_market_key(value: Any) -> str:
    return normalize_key(str(value or ""))


def model_path_for_market(market: Any) -> Path:
    key = model_market_key(market)
    if not key:
        return DEFAULT_MODEL_PATH
    return MODEL_DIR / f"prop_model_{key}.joblib"


def metadata_path_for_model(model_path: str | Path) -> Path:
    path = Path(model_path)
    return path.with_name(f"{path.stem}_features.json")


def infer_market_from_training_path(csv_path: str | Path) -> str:
    stem = Path(csv_path).stem
    suffix = "_training"
    if stem.endswith(suffix):
        return model_market_key(stem[: -len(suffix)])
    return ""


def first_value(row: dict[str, Any], aliases: Iterable[str], default: Any = "") -> Any:
    normalized = {normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        key = normalize_key(alias)
        if key in normalized and str(normalized[key]).strip() != "":
            return normalized[key]
    return default


# Returns math.nan for missing values so sklearn imputers and missing indicators fire.
# Do NOT change this default to 0.0; aggregation modules have their own to_float().
def to_float(value: Any, default: float = math.nan) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return default
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        return float(text)
    except ValueError:
        return default


def to_binary_target(row: dict[str, Any]) -> int:
    explicit = str(first_value(row, TARGET_ALIASES, "")).strip().lower()
    if explicit in {"1", "true", "yes", "y", "win", "won", "over", "hit"}:
        return 1
    if explicit in {"0", "false", "no", "n", "loss", "lost", "under", "miss"}:
        return 0

    actual = to_float(first_value(row, ACTUAL_ALIASES, ""), math.nan)
    line = to_float(first_value(row, LINE_ALIASES, ""), math.nan)
    if not math.isnan(actual) and not math.isnan(line):
        return 1 if actual > line else 0
    raise ValueError("Training row needs an over/result column or actual stat plus line.")


def implied_probability_from_american(odds: float) -> float:
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return 0.5


def american_from_probability(probability: float) -> int:
    probability = min(max(probability, 0.001), 0.999)
    if probability >= 0.5:
        return round(-100 * probability / (1 - probability))
    return round(100 * (1 - probability) / probability)


def expected_value_per_unit(probability: float, american_odds: float) -> float:
    probability = min(max(probability, 0.0), 1.0)
    profit = 100.0 / abs(american_odds) if american_odds < 0 else american_odds / 100.0
    return probability * profit - (1.0 - probability)


def row_to_features(row: dict[str, Any], feature_columns: list[str]) -> dict[str, float]:
    values: dict[str, float] = {}
    for feature in feature_columns:
        if feature == "line":
            values[feature] = to_float(first_value(row, LINE_ALIASES, row.get(feature, math.nan)))
        elif feature == "book_implied_probability":
            values[feature] = to_float(first_value(row, [feature, "implied_probability"], row.get(feature, math.nan)))
        elif feature == "line_move":
            values[feature] = to_float(first_value(row, [feature, "lineMove"], row.get(feature, math.nan)))
        elif feature == "odds_move":
            values[feature] = to_float(first_value(row, [feature, "oddsMove"], row.get(feature, math.nan)))
        elif feature == "vig_pct":
            values[feature] = to_float(first_value(row, [feature, "vig", "vigPercent"], row.get(feature, math.nan)))
        elif feature == "wind_out_score":
            values[feature] = to_float(first_value(row, [feature, "windOutScore"], row.get(feature, math.nan)))
        elif feature == "wind_out_flag":
            values[feature] = to_float(first_value(row, [feature, "windOutFlag"], row.get(feature, math.nan)))
        elif feature == "turf_flag":
            values[feature] = to_float(first_value(row, [feature, "turfFlag"], row.get(feature, math.nan)))
        elif feature == "cold_game_flag":
            values[feature] = to_float(first_value(row, [feature, "coldGameFlag"], row.get(feature, math.nan)))
        else:
            values[feature] = to_float(first_value(row, [feature], row.get(feature, math.nan)))

    odds = to_float(first_value(row, ODDS_ALIASES, row.get("american_odds", math.nan)))
    if not math.isnan(odds) and odds != 0:
        values["book_implied_probability"] = implied_probability_from_american(odds)
    elif math.isnan(values.get("book_implied_probability", math.nan)):
        values["book_implied_probability"] = 0.5

    under_odds = to_float(first_value(row, UNDER_ODDS_ALIASES, row.get("under_odds", math.nan)))
    if math.isnan(values.get("vig_pct", math.nan)) and not math.isnan(odds) and not math.isnan(under_odds) and odds and under_odds:
        values["vig_pct"] = round((implied_probability_from_american(odds) + implied_probability_from_american(under_odds) - 1.0) * 100, 2)

    for feature in MISSING_INDICATOR_FEATURES:
        value = values.get(feature, math.nan)
        values[f"{feature}_missing"] = 1.0 if isinstance(value, float) and math.isnan(value) else 0.0
    return values


@dataclass
class MlPrediction:
    probability: float
    fair_odds: int
    implied_probability: float
    edge: float
    expected_value: float
    model_version: str
    features_used: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "probability": self.probability,
            "fairOdds": self.fair_odds,
            "impliedProbability": self.implied_probability,
            "edge": self.edge,
            "expectedValue": self.expected_value,
            "modelVersion": self.model_version,
            "featuresUsed": self.features_used,
        }


def load_training_rows(csv_path: str | Path) -> list[dict[str, Any]]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def train_model(
    csv_path: str | Path,
    model_path: str | Path | None = None,
    market: str = "",
) -> dict[str, Any]:
    try:
        from joblib import dump
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.metrics import brier_score_loss, roc_auc_score
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler
    except ImportError as error:
        raise RuntimeError("Install ML dependencies first: python -m pip install -r requirements.txt") from error

    rows = load_training_rows(csv_path)
    if len(rows) < 25:
        raise ValueError("Add at least 25 historical prop rows before training. 100+ is better.")

    market_key = model_market_key(market) or infer_market_from_training_path(csv_path)
    if not market_key and rows:
        market_key = model_market_key(first_value(rows[0], ["market"], ""))
    resolved_model_path = Path(model_path) if model_path is not None else model_path_for_market(market_key)
    resolved_metadata_path = metadata_path_for_model(resolved_model_path)

    numeric_features = DEFAULT_FEATURE_COLUMNS + [f"{f}_missing" for f in MISSING_INDICATOR_FEATURES]
    feature_rows: list[dict[str, Any]] = []
    targets: list[int] = []

    for row in rows:
        normalized_row = {normalize_key(key): value for key, value in row.items()}
        features = row_to_features(normalized_row, DEFAULT_FEATURE_COLUMNS)
        for text_column in TEXT_COLUMNS:
            features[text_column] = str(first_value(normalized_row, [text_column], "")).strip().lower()
        feature_rows.append(features)
        targets.append(to_binary_target(normalized_row))

    import pandas as pd

    frame = pd.DataFrame(feature_rows)
    y = pd.Series(targets)
    if len(set(y)) < 2:
        raise ValueError(
            "Training data must contain both winning (over/hit) and losing (under/miss) rows. "
            f"Current data has only one class: {set(y)}."
        )

    def row_date(row: dict[str, Any]) -> Any:
        return first_value(row, ["date", "game_date", "gameDate", "event_date", "start_time"], "")

    date_values = pd.to_datetime([row_date(row) for row in rows], errors="coerce")
    if date_values.notna().any():
        order = date_values.fillna(pd.Timestamp.max).argsort(kind="mergesort")
        frame = frame.iloc[order].reset_index(drop=True)
        y = y.iloc[order].reset_index(drop=True)
        split_note = "chronological_date_sort"
    else:
        split_note = "input_order_no_date_column_found"

    split_index = max(1, int(len(frame) * 0.75))
    split_index = min(split_index, len(frame) - 1)
    x_train = frame.iloc[:split_index].reset_index(drop=True)
    x_test = frame.iloc[split_index:].reset_index(drop=True)
    y_train = y.iloc[:split_index].reset_index(drop=True)
    y_test = y.iloc[split_index:].reset_index(drop=True)

    x_calibrate = None
    y_calibrate = None
    if len(frame) >= 60:
        train_end = max(1, int(len(frame) * 0.60))
        calibrate_end = max(train_end + 1, int(len(frame) * 0.80))
        calibrate_end = min(calibrate_end, len(frame) - 1)
        x_train = frame.iloc[:train_end].reset_index(drop=True)
        y_train = y.iloc[:train_end].reset_index(drop=True)
        x_calibrate = frame.iloc[train_end:calibrate_end].reset_index(drop=True)
        y_calibrate = y.iloc[train_end:calibrate_end].reset_index(drop=True)
        x_test = frame.iloc[calibrate_end:].reset_index(drop=True)
        y_test = y.iloc[calibrate_end:].reset_index(drop=True)
        split_note = f"{split_note}_60_20_20_calibrated"

    if len(set(y_train)) < 2:
        raise ValueError(
            "Chronological training fold has only one target class. Add more earlier rows with both outcomes "
            "or use a wider historical training file."
        )

    def one_hot_encoder() -> OneHotEncoder:
        try:
            return OneHotEncoder(handle_unknown="ignore", min_frequency=2, sparse_output=False)
        except TypeError:  # scikit-learn < 1.2
            return OneHotEncoder(handle_unknown="ignore", min_frequency=2, sparse=False)

    def make_preprocessor(kind: str) -> ColumnTransformer:
        if kind == "hist_gradient_boosting":
            numeric_transformer: str | Pipeline = "passthrough"
        elif kind == "logistic_regression":
            numeric_transformer = Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ])
        else:
            numeric_transformer = Pipeline([("impute", SimpleImputer(strategy="median"))])

        return ColumnTransformer(
            transformers=[
                ("numeric", numeric_transformer, numeric_features),
                ("text", one_hot_encoder(), TEXT_COLUMNS),
            ],
            remainder="drop",
        )

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=250, min_samples_leaf=8, random_state=42, class_weight="balanced"
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=150, learning_rate=0.05, random_state=42
        ),
    }

    def evaluate_probabilities(y_true: pd.Series, probabilities: Any) -> dict[str, float]:
        try:
            auc = roc_auc_score(y_true, probabilities) if len(set(y_true)) == 2 else 0.5
        except ValueError:
            auc = 0.5
        brier = brier_score_loss(y_true, probabilities)
        return {"auc": float(auc), "brier": float(brier), "score": float(auc - brier)}

    def cv_score_model(name: str, estimator: Any) -> dict[str, float]:
        class_counts = y_train.value_counts()
        max_splits = min(5, len(x_train) - 1, int(class_counts.min()) if len(class_counts) > 1 else 0)
        if max_splits < 2:
            return {"auc": 0.5, "brier": 1.0, "score": -0.5, "folds": 0.0}

        fold_metrics = []
        splitter = TimeSeriesSplit(n_splits=max_splits)
        for train_idx, valid_idx in splitter.split(x_train):
            fold_y_train = y_train.iloc[train_idx]
            fold_y_valid = y_train.iloc[valid_idx]
            if len(set(fold_y_train)) < 2 or len(set(fold_y_valid)) < 2:
                continue
            pipeline = Pipeline([("features", make_preprocessor(name)), ("model", estimator)])
            pipeline.fit(x_train.iloc[train_idx], fold_y_train)
            probabilities = pipeline.predict_proba(x_train.iloc[valid_idx])[:, 1]
            fold_metrics.append(evaluate_probabilities(fold_y_valid, probabilities))

        if not fold_metrics:
            return {"auc": 0.5, "brier": 1.0, "score": -0.5, "folds": 0.0}

        return {
            "auc": float(sum(item["auc"] for item in fold_metrics) / len(fold_metrics)),
            "brier": float(sum(item["brier"] for item in fold_metrics) / len(fold_metrics)),
            "score": float(sum(item["score"] for item in fold_metrics) / len(fold_metrics)),
            "folds": float(len(fold_metrics)),
        }

    best_name = ""
    best_score = -float("inf")
    metrics: dict[str, dict[str, float]] = {}

    for name, estimator in candidates.items():
        cv_metrics = cv_score_model(name, estimator)
        metrics[name] = {f"cv_{key}": value for key, value in cv_metrics.items()}
        if cv_metrics["score"] > best_score:
            best_name = name
            best_score = cv_metrics["score"]

    if not best_name:
        raise RuntimeError("Could not select an ML model from the provided rows.")

    best_pipeline = Pipeline([("features", make_preprocessor(best_name)), ("model", candidates[best_name])])
    best_pipeline.fit(x_train, y_train)

    final_model: Any = best_pipeline
    calibration_note = "not_applied"
    if x_calibrate is not None and y_calibrate is not None and len(set(y_calibrate)) == 2:
        import warnings
        method = "isotonic" if len(x_calibrate) >= 500 else "sigmoid"

        # sklearn 1.6+ removed cv="prefit". Use FrozenEstimator when available.
        # If calibration is not compatible, keep the already-fit model instead of failing training.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    from sklearn.frozen import FrozenEstimator
                    calibrated = CalibratedClassifierCV(
                        estimator=FrozenEstimator(best_pipeline),
                        method=method,
                    )
                except Exception:
                    calibrated = CalibratedClassifierCV(
                        estimator=best_pipeline,
                        method=method,
                        cv=3,
                        ensemble=False,
                    )
                calibrated.fit(x_calibrate, y_calibrate)

            final_model = calibrated
            calibration_note = method
        except Exception as error:
            final_model = best_pipeline
            calibration_note = f"skipped: {error}"

    test_probabilities = final_model.predict_proba(x_test)[:, 1]
    metrics[best_name].update({f"test_{key}": value for key, value in evaluate_probabilities(y_test, test_probabilities).items()})

    resolved_model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(final_model, resolved_model_path)

    metadata = {
        "market": market_key,
        "modelPath": str(resolved_model_path),
        "bestModel": best_name,
        "numericFeatures": numeric_features,
        "textFeatures": TEXT_COLUMNS,
        "rows": len(rows),
        "trainRows": len(x_train),
        "calibrationRows": 0 if x_calibrate is None else len(x_calibrate),
        "testRows": len(x_test),
        "split": split_note,
        "calibration": calibration_note,
        "metrics": metrics,
    }
    resolved_metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def predict_from_row(
    row: dict[str, Any],
    model_path: str | Path | None = None,
    market: str = "",
) -> MlPrediction:
    try:
        from joblib import load
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("Install ML dependencies first: python -m pip install -r requirements.txt") from error

    market_key = model_market_key(market) or model_market_key(first_value(row, ["market"], ""))
    if model_path is None:
        candidate = model_path_for_market(market_key)
        if candidate.exists() or not DEFAULT_MODEL_PATH.exists():
            resolved_model_path = candidate
        else:
            resolved_model_path = DEFAULT_MODEL_PATH
    else:
        resolved_model_path = Path(model_path)

    if not resolved_model_path.exists():
        raise FileNotFoundError(f"No trained model found at {resolved_model_path}. Run train_model first.")

    metadata_path = metadata_path_for_model(resolved_model_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    feature_columns = list(metadata.get("numericFeatures") or (DEFAULT_FEATURE_COLUMNS + ["book_implied_probability"]))
    numeric_base = [feature for feature in feature_columns if not feature.endswith("_missing")]

    features = row_to_features(row, numeric_base)
    for text_column in TEXT_COLUMNS:
        features[text_column] = str(first_value(row, [text_column], "")).strip().lower()

    pipeline = load(resolved_model_path)
    probability = float(pipeline.predict_proba(pd.DataFrame([features]))[0][1])
    odds = to_float(first_value(row, ODDS_ALIASES, row.get("american_odds", -110)), -110)
    implied = implied_probability_from_american(odds)

    return MlPrediction(
        probability=probability,
        fair_odds=american_from_probability(probability),
        implied_probability=implied,
        edge=probability - implied,
        expected_value=expected_value_per_unit(probability, odds),
        model_version=str(metadata.get("bestModel") or "unknown"),
        features_used=feature_columns + TEXT_COLUMNS,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train or run the free ML prop model.")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train")
    train.add_argument("csv", help="Historical prop result CSV")
    train.add_argument("--market", default="", help="Market key for the model artifact, e.g. pitcher_strikeouts")
    train.add_argument("--model-path", default="", help="Optional explicit model output path")

    predict = sub.add_parser("predict")
    predict.add_argument("--json", required=True, help="JSON object containing features for one prop")
    predict.add_argument("--market", default="", help="Market key for selecting a trained model")
    predict.add_argument("--model-path", default="", help="Optional explicit model path")

    args = parser.parse_args()
    if args.command == "train":
        print(json.dumps(train_model(args.csv, args.model_path or None, market=args.market), indent=2))
    elif args.command == "predict":
        print(json.dumps(predict_from_row(json.loads(args.json), args.model_path or None, market=args.market).to_dict(), indent=2))


if __name__ == "__main__":
    main()
