from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings, settings as default_settings

DEFAULT_FEATURE_COLUMNS = [
    "line",
    "book_implied_probability",
    "line_move",
    "odds_move",
    "vig_pct",
    "recent_games",
    "recent_rate",
    "season_rate",
    "rolling_avg_5",
    "rolling_avg_10",
    "rolling_avg_15",
    "rolling_total_bases_10",
    "rolling_hr_rate_15",
    "rolling_k_rate_10",
    "batter_babip",
    "batter_k_rate",
    "batter_walk_rate",
    "batter_days_rest",
    "batter_avg_home",
    "batter_avg_away",
    "barrel_rate",
    "hard_hit_rate",
    "xwoba",
    "xba",
    "xslg",
    "batter_ld_rate",
    "batter_gb_rate",
    "batter_sprint_speed",
    "batter_avg_vs_hand",
    "batter_k_rate_vs_hand",
    "batter_recent_hits_vs_lhp",
    "batter_recent_hits_vs_rhp",
    "pitcher_k_rate",
    "pitcher_walk_rate",
    "pitcher_hr_rate",
    "pitcher_babip",
    "pitcher_days_rest",
    "pitcher_velo_delta",
    "pitcher_avg_allowed_vs_hand",
    "team_k_rate",
    "team_walk_rate",
    "opponent_rate",
    "opponent_bullpen_era_7d",
    "ump_k_rate",
    "ump_zone_size_zscore",
    "ump_favor_batter_score",
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
    "market",
    "player",
    "pitcher",
    "team",
    "opponent",
    "throws",
    "bats",
    "venue",
    "roof",
    "platoon_matchup",
]

LINE_ALIASES = ["line", "sportsbook_line", "prop_line"]
ODDS_ALIASES = ["american_odds", "americanOdds", "odds", "price", "over_odds", "overOdds"]
UNDER_ODDS_ALIASES = ["under_odds", "underOdds", "under_price", "underPrice"]


@dataclass(frozen=True)
class PlayerPropModelPrediction:
    probability: float
    fair_odds: int
    implied_probability: float
    edge: float
    expected_value: float
    model_version: str
    features_used: list[str]
    model_path: Path
    warnings: list[str] | None = None


def normalize_key(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def model_market_key(value: Any) -> str:
    return normalize_key(str(value or ""))


def first_value(row: dict[str, Any], aliases: Iterable[str], default: Any = "") -> Any:
    normalized = {normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        key = normalize_key(alias)
        if key in normalized and str(normalized[key]).strip() != "":
            return normalized[key]
    return default


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


def model_path_for_market(market: Any, *, settings: Settings = default_settings) -> Path:
    key = model_market_key(market)
    if not key:
        raise ValueError("Market key is required for exact player prop model scoring.")
    return settings.model_dir / f"prop_model_{key}.joblib"


def metadata_path_for_model(model_path: str | Path) -> Path:
    path = Path(model_path)
    return path.with_name(f"{path.stem}_features.json")


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


def score_exact_market_model(
    row: dict[str, Any],
    *,
    market: str = "",
    model_path: str | Path | None = None,
    settings: Settings = default_settings,
) -> PlayerPropModelPrediction:
    try:
        from joblib import load
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("Install ML dependencies first: python -m pip install -r requirements.txt") from error

    market_key = model_market_key(market) or model_market_key(first_value(row, ["market"], ""))
    resolved_model_path = Path(model_path) if model_path is not None else model_path_for_market(market_key, settings=settings)
    if not resolved_model_path.is_file():
        raise FileNotFoundError(f"Missing market-specific model artifact for {market_key or 'unknown_market'} at {resolved_model_path}.")

    metadata_path = metadata_path_for_model(resolved_model_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    feature_columns = list(metadata.get("numericFeatures") or (DEFAULT_FEATURE_COLUMNS + ["book_implied_probability"]))
    numeric_base = [feature for feature in feature_columns if not feature.endswith("_missing")]

    features = row_to_features(row, numeric_base)
    for text_column in TEXT_COLUMNS:
        features[text_column] = str(first_value(row, [text_column], "")).strip().lower()

    pipeline = load(resolved_model_path)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        probability = float(pipeline.predict_proba(pd.DataFrame([features]))[0][1])
    odds = to_float(first_value(row, ODDS_ALIASES, row.get("american_odds", -110)), -110)
    implied = implied_probability_from_american(odds)

    return PlayerPropModelPrediction(
        probability=probability,
        fair_odds=american_from_probability(probability),
        implied_probability=implied,
        edge=probability - implied,
        expected_value=expected_value_per_unit(probability, odds),
        model_version=str(metadata.get("bestModel") or "unknown"),
        features_used=feature_columns + TEXT_COLUMNS,
        model_path=resolved_model_path,
        warnings=_dedupe_warning_messages(captured),
    )


def _dedupe_warning_messages(captured: list[warnings.WarningMessage]) -> list[str]:
    messages: list[str] = []
    seen: set[str] = set()
    for item in captured:
        text = str(item.message).strip()
        if text and text not in seen:
            seen.add(text)
            messages.append(text)
    return messages
