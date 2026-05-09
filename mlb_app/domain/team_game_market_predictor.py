from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
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

MARKET_FAMILY = {
    "moneyline": "moneyline",
    "moneyline_first_five": "moneyline",
    "run_line": "spread",
    "run_line_first_five": "spread",
    "run_line_first_inning": "spread",
    "game_total_runs": "total",
    "first_five_total_runs": "total",
    "first_inning_total_runs": "total",
    "team_total_runs": "team_total",
    "team_first_to_score": "first_score",
}


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


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace("+", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def american_to_implied(odds: Any) -> float:
    value = to_float(odds, 0.0)
    if value == 0:
        return 0.0
    if value > 0:
        return 100.0 / (value + 100.0)
    return abs(value) / (abs(value) + 100.0)


def confidence_from_edge(edge: float) -> str:
    abs_edge = abs(float(edge))
    if abs_edge >= 0.12:
        return "High"
    if abs_edge >= 0.06:
        return "Medium"
    return "Low"


def model_path_for(market: str, season: int = 2026) -> Path:
    return MODEL_DIR / f"{market}_{season}.joblib"


def load_market_model(market: str, season: int = 2026) -> dict[str, Any] | None:
    path = model_path_for(market, season)
    if not path.exists():
        return None
    try:
        payload = joblib.load(path)
        if isinstance(payload, dict) and "model" in payload:
            return payload
    except Exception:
        return None
    return None


def normalize_feature_row(row: dict[str, Any], features: list[str]) -> pd.DataFrame:
    market = clean(row.get("market"))
    family = MARKET_FAMILY.get(market, "other")

    team = clean(row.get("team") or row.get("gradedTeam"))
    home = clean(row.get("home"))
    away = clean(row.get("away"))
    side = clean(row.get("side") or row.get("outcomeName") or row.get("outcome")).lower()

    feature_values = {
        "line": to_float(row.get("line")),
        "americanOdds": to_float(row.get("americanOdds")),
        "sportsbookImpliedProbability": american_to_implied(row.get("americanOdds")),
        "isHomeTeam": 1 if team and home and team == home else 0,
        "isAwayTeam": 1 if team and away and team == away else 0,
        "isOver": 1 if "over" in side else 0,
        "isUnder": 1 if "under" in side else 0,
        "isMoneyline": 1 if family == "moneyline" else 0,
        "isSpread": 1 if family == "spread" else 0,
        "isTotal": 1 if family == "total" else 0,
        "isTeamTotal": 1 if family == "team_total" else 0,
        "isFirstScore": 1 if family == "first_score" else 0,
    }

    return pd.DataFrame([{feature: feature_values.get(feature, 0.0) for feature in features}])


def predict_team_game_market(row: dict[str, Any], season: int = 2026) -> dict[str, Any]:
    market = clean(row.get("market"))
    payload = load_market_model(market, season=season)

    implied = american_to_implied(row.get("americanOdds"))

    base = {
        "market": market,
        "team": clean(row.get("team") or row.get("gradedTeam")),
        "opponent": clean(row.get("opponent") or row.get("gradedOpponent")),
        "line": to_float(row.get("line")),
        "americanOdds": to_float(row.get("americanOdds")),
        "sportsbookImpliedProbability": implied,
        "projectedProbability": None,
        "edge": None,
        "edgePercent": None,
        "confidence": "Unavailable",
        "modelName": "",
        "modelAvailable": False,
        "modelPath": str(model_path_for(market, season=season)),
    }

    if not payload:
        return base

    model = payload.get("model")
    features = payload.get("features") or DEFAULT_FEATURES
    frame = normalize_feature_row(row, features)

    try:
        proba = model.predict_proba(frame)
        projected = float(proba[:, 1][0]) if proba.shape[1] > 1 else float(proba[:, 0][0])
    except Exception:
        return base

    edge = projected - implied

    base.update({
        "projectedProbability": projected,
        "edge": edge,
        "edgePercent": edge * 100.0,
        "confidence": confidence_from_edge(edge),
        "modelName": clean(payload.get("modelName")),
        "modelAvailable": True,
    })

    return base


def predict_rows(rows: list[dict[str, Any]], season: int = 2026) -> list[dict[str, Any]]:
    return [predict_team_game_market(row, season=season) for row in rows]
