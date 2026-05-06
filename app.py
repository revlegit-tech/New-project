from __future__ import annotations
from local_env import load_local_env
load_local_env()

import csv
import hashlib
import ipaddress
import io
import json
import math
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse


def pipeline_date_from_query(query: dict[str, list[str]]) -> str:
    return query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]


def pipeline_create_game_odds_template(date_label: str) -> dict[str, Any]:
    from build_game_odds_template import OUTPUT_DIR, build_template, mlb_schedule, save_template

    games = mlb_schedule(date_label)
    if not games:
        raise ValueError(f"No MLB games found for {date_label}")

    rows = build_template(date_label, games)
    output_path = OUTPUT_DIR / f"game_odds_template_{date_label}.csv"
    save_template(output_path, rows)

    return {
        "date": date_label,
        "games": len(games),
        "rows": len(rows),
        "output": str(output_path),
    }


def pipeline_grade_props(date_label: str) -> dict[str, Any]:
    from grade_propline_props import grade_props

    return grade_props(date_label)


def pipeline_merge_game_odds(date_label: str) -> dict[str, Any]:
    from merge_game_odds_features import merge_features

    props_path = DATA_DIR / "training" / "historical_props.csv"
    game_odds_path = DATA_DIR / "imports" / f"game_odds_template_{date_label}.csv"
    output_path = DATA_DIR / "training" / "historical_props_with_game_odds.csv"

    return merge_features(props_path, game_odds_path, output_path)


def pipeline_prepare_strikeouts() -> dict[str, Any]:
    from prepare_strikeout_training import prepare

    input_path = DATA_DIR / "training" / "historical_props_with_game_odds.csv"
    output_path = DATA_DIR / "training" / "pitcher_strikeouts_training.csv"

    return prepare(input_path, output_path)


def pipeline_train_strikeouts() -> dict[str, Any]:
    training_path = DATA_DIR / "training" / "pitcher_strikeouts_training.csv"
    return train_model(training_path, market="pitcher_strikeouts")




def pipeline_autofill_game_odds(date_label: str) -> dict[str, Any]:
    from autofill_game_odds_from_propline import autofill_template

    template_path = DATA_DIR / "imports" / f"game_odds_template_{date_label}.csv"
    return autofill_template(template_path, date_label)


def pipeline_run_after_game(date_label: str) -> dict[str, Any]:
    grade_result = pipeline_grade_props(date_label)
    merge_result = pipeline_merge_game_odds(date_label)
    prepare_result = pipeline_prepare_strikeouts()
    train_result = pipeline_train_strikeouts()

    return {
        "date": date_label,
        "grade": grade_result,
        "merge": merge_result,
        "prepare": prepare_result,
        "train": train_result,
    }




def moneyline_implied_probability(odds: float) -> float:
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return 0.5


def moneyline_favorite_status(team_moneyline: float, opponent_moneyline: float) -> str:
    if not team_moneyline and not opponent_moneyline:
        return ""
    if team_moneyline < opponent_moneyline:
        return "favorite"
    if team_moneyline > opponent_moneyline:
        return "underdog"
    return "even"


def moneyline_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    return query.get(key, [default])[0]


def moneyline_query_float(query: dict[str, list[str]], key: str, default: float = 0.0) -> float:
    try:
        return float(moneyline_query_value(query, key, str(default)))
    except ValueError:
        return default


def moneyline_prediction_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from ml_moneyline_model import predict_from_row

    team = moneyline_query_value(query, "team").upper()
    opponent = moneyline_query_value(query, "opponent").upper()
    home_away = moneyline_query_value(query, "home_away", "home")

    team_moneyline = moneyline_query_float(query, "team_moneyline")
    opponent_moneyline = moneyline_query_float(query, "opponent_moneyline")
    game_total = moneyline_query_float(query, "game_total")
    open_team_moneyline = moneyline_query_float(query, "open_team_moneyline")
    close_team_moneyline = moneyline_query_float(query, "close_team_moneyline", team_moneyline)
    open_game_total = moneyline_query_float(query, "open_game_total")
    close_game_total = moneyline_query_float(query, "close_game_total", game_total)
    team_implied_runs = moneyline_query_float(query, "team_implied_runs")
    opponent_implied_runs = moneyline_query_float(query, "opponent_implied_runs")

    implied_probability = moneyline_implied_probability(team_moneyline)
    favorite_status = moneyline_favorite_status(team_moneyline, opponent_moneyline)

    row = {
        "team": team,
        "opponent": opponent,
        "home_away": home_away,
        "team_moneyline": team_moneyline,
        "opponent_moneyline": opponent_moneyline,
        "game_total": game_total,
        "open_team_moneyline": open_team_moneyline,
        "close_team_moneyline": close_team_moneyline,
        "moneyline_move": close_team_moneyline - open_team_moneyline if open_team_moneyline and close_team_moneyline else 0,
        "open_game_total": open_game_total,
        "close_game_total": close_game_total,
        "total_move": close_game_total - open_game_total if open_game_total and close_game_total else 0,
        "moneyline_implied_probability": implied_probability,
        "favorite_status": favorite_status,
        "team_implied_runs": team_implied_runs,
        "opponent_implied_runs": opponent_implied_runs,
        "opponent_implied_runs_proxy": opponent_implied_runs,
    }

    prediction = predict_from_row(row)
    model_probability = float(prediction["teamWinProbability"])
    edge = model_probability - implied_probability

    return {
        **prediction,
        "team": team,
        "opponent": opponent,
        "homeAway": home_away,
        "teamMoneyline": team_moneyline,
        "opponentMoneyline": opponent_moneyline,
        "gameTotal": game_total,
        "sportsbookImpliedProbability": implied_probability,
        "sportsbookImpliedPercent": round(implied_probability * 100, 2),
        "modelEdge": edge,
        "modelEdgePercent": round(edge * 100, 2),
        "favoriteStatus": favorite_status,
        "recommendation": "positive edge" if edge > 0 else "negative edge",
    }




def prop_ml_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    return query.get(key, [default])[0]


def prop_ml_query_float(query: dict[str, list[str]], key: str, default: float = 0.0) -> float:
    try:
        return float(prop_ml_query_value(query, key, str(default)))
    except ValueError:
        return default






DAILY_WORKFLOW_MARKETS = [
    "pitcher_strikeouts",
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]


def daily_workflow_date(query: dict[str, list[str]]) -> str:
    return query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]


def daily_workflow_before_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    date_label = daily_workflow_date(query)

    props_result = propline_props_payload({
        "markets": [",".join(DAILY_WORKFLOW_MARKETS)],
        "date": [date_label],
    })

    template_result = pipeline_create_game_odds_template(date_label)

    try:
        autofill_result = pipeline_autofill_game_odds(date_label)
    except Exception as error:
        autofill_result = {
            "error": str(error),
            "note": "Template was created, but PropLine game odds could not be auto-filled.",
        }

    return {
        "date": date_label,
        "step": "before",
        "props": props_result,
        "template": template_result,
        "autofill": autofill_result,
        "nextStep": "Review auto-filled odds if needed, then run After Game Update when games are final.",
    }


def daily_workflow_after_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    import subprocess
    import sys

    date_label = daily_workflow_date(query)
    season = int(date_label[:4])

    result: dict[str, Any] = {
        "date": date_label,
        "step": "after",
        "grade": None,
        "merge": None,
        "playerPropMarkets": [],
        "moneyline": None,
    }

    result["grade"] = pipeline_grade_props(date_label)
    result["merge"] = pipeline_merge_game_odds(date_label)

    for market in DAILY_WORKFLOW_MARKETS:
        command = [
            sys.executable,
            str(ROOT / "prepare_market_training.py"),
            "--market",
            market,
            "--train",
        ]

        completed = subprocess.run(command, capture_output=True, text=True)

        result["playerPropMarkets"].append({
            "market": market,
            "returnCode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "trained": completed.returncode == 0 and "Training model..." in completed.stdout,
        })

    moneyline_command = [
        sys.executable,
        str(ROOT / "prepare_moneyline_training.py"),
        "--season",
        str(season),
        "--start-date",
        f"{season}-03-01",
        "--end-date",
        date_label,
        "--train",
    ]

    moneyline_completed = subprocess.run(moneyline_command, capture_output=True, text=True)

    result["moneyline"] = {
        "returnCode": moneyline_completed.returncode,
        "stdout": moneyline_completed.stdout,
        "stderr": moneyline_completed.stderr,
        "trained": moneyline_completed.returncode == 0,
    }

    return result


def prop_ml_market_status_payload() -> dict[str, Any]:
    import csv
    from collections import Counter

    markets = [
        "pitcher_strikeouts",
        "batter_hits",
        "batter_total_bases",
        "batter_home_runs",
        "pitcher_hits_allowed",
        "pitcher_earned_runs",
    ]

    rows = []
    for market in markets:
        path = DATA_DIR / "training" / f"{market}_training.csv"
        total = 0
        counts: Counter[str] = Counter()

        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    total += 1
                    value = str(row.get("over", "")).strip()
                    if value in {"0", "1"}:
                        counts[value] += 1

        can_train = counts.get("0", 0) > 0 and counts.get("1", 0) > 0 and total >= 25
        model_path = model_path_for_market(market)
        metadata_path = metadata_path_for_model(model_path)

        rows.append({
            "market": market,
            "trainingRows": total,
            "classCounts": dict(counts),
            "canTrain": can_train,
            "modelTrained": model_path.exists(),
            "modelPath": str(model_path),
            "metadataPath": str(metadata_path),
            "status": "trained" if model_path.exists() else ("ready to train" if can_train else "needs more data"),
        })

    return {
        "markets": rows,
        "readyMarkets": [row["market"] for row in rows if row["canTrain"]],
        "notReadyMarkets": [row["market"] for row in rows if not row["canTrain"]],
        "trainedMarkets": [row["market"] for row in rows if row["modelTrained"]],
    }








def workflow_summaries_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    import json

    health_dir = DATA_DIR / "health"

    summary_files = {
        "dailyHealth": health_dir / "latest_daily_health.json",
        "dailyGrading": health_dir / "latest_grading_summary.json",
        "weeklyRepair": health_dir / "latest_weekly_repair.json",
    }

    summaries: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []

    for key, path in summary_files.items():
        item: dict[str, Any] = {
            "key": key,
            "exists": path.exists(),
            "file": str(path),
            "size": path.stat().st_size if path.exists() else 0,
            "ok": False,
            "date": "",
            "checkedAt": "",
            "warnings": [],
            "errors": [],
            "payload": None,
        }

        if not path.exists():
            item["warnings"].append(f"{path.name} does not exist yet.")
            warnings.append(f"{key}: {path.name} does not exist yet.")
            summaries[key] = item
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            item["payload"] = payload
            item["ok"] = bool(payload.get("ok", True))
            item["date"] = str(payload.get("date", ""))
            item["checkedAt"] = str(payload.get("checkedAt", ""))
            item["warnings"] = list(payload.get("warnings") or [])
            item["errors"] = list(payload.get("errors") or [])

            if not item["ok"]:
                errors.append(f"{key}: latest summary is not OK.")
            for warning in item["warnings"]:
                warnings.append(f"{key}: {warning}")
            for error in item["errors"]:
                errors.append(f"{key}: {error}")

        except Exception as error:
            item["ok"] = False
            item["errors"].append(str(error))
            errors.append(f"{key}: could not read {path.name}: {error}")

        summaries[key] = item

    return {
        "ok": not errors,
        "healthDir": str(health_dir),
        "summaries": summaries,
        "warnings": warnings,
        "errors": errors,
    }

def grading_health_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    import json

    requested_date = query.get("date", [""])[0]
    health_dir = DATA_DIR / "health"
    latest_path = health_dir / "latest_grading_summary.json"

    if not latest_path.exists():
        return {
            "ok": False,
            "exists": False,
            "file": str(latest_path),
            "requestedDate": requested_date,
            "warnings": ["No grading summary exists yet. Run Daily playerboard grading first."],
        }

    payload = json.loads(latest_path.read_text(encoding="utf-8", errors="ignore"))
    counts = payload.get("counts") or {}
    warnings = list(payload.get("warnings") or [])
    errors = list(payload.get("errors") or [])

    if requested_date and payload.get("date") != requested_date:
        warnings.append(
            f"Latest grading summary is for {payload.get('date')}, not requested date {requested_date}."
        )

    backtest_rows = int(counts.get("backtestRowsForDate") or 0)
    graded_backtest = int(counts.get("gradedBacktestRowsForDate") or 0)
    ml_rows = int(counts.get("mlRowsForDate") or 0)
    graded_ml = int(counts.get("gradedMlRowsForDate") or 0)

    ok = bool(payload.get("ok", True)) and not errors
    if backtest_rows > 0 and graded_backtest <= 0:
        ok = False
    if ml_rows > 0 and graded_ml <= 0:
        ok = False

    return {
        **payload,
        "ok": ok,
        "exists": True,
        "file": str(latest_path),
        "requestedDate": requested_date,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "backtestRowsForDate": backtest_rows,
            "gradedBacktestRowsForDate": graded_backtest,
            "mlRowsForDate": ml_rows,
            "gradedMlRowsForDate": graded_ml,
        },
    }

def data_health_query_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from data_health import data_health_payload

    date_label = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
    return data_health_payload(date_label)




def saved_games_query_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from data_health import saved_games_payload

    date_label = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
    return saved_games_payload(date_label)


def saved_props_for_game_query_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from data_health import prop_rows_for_game_payload

    date_label = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
    market = query.get("market", [""])[0]
    away = query.get("away", [""])[0]
    home = query.get("home", [""])[0]

    return prop_rows_for_game_payload(date_label, market, away, home)


def saved_props_query_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from data_health import prop_rows_payload

    date_label = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
    market = query.get("market", [""])[0]
    return prop_rows_payload(date_label, market)


def save_all_data_prediction_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from data_health import save_prediction_payload
    from unified_prop_context import all_data_predict

    row = {
        "date": query.get("date", [""])[0],
        "market": query.get("market", ["batter_hits"])[0],
        "player": query.get("player", [""])[0],
        "team": query.get("team", [""])[0],
        "opponent": query.get("opponent", [""])[0],
        "pitcher": query.get("pitcher", [""])[0],
        "line": query.get("line", ["0.5"])[0],
        "american_odds": query.get("american_odds", ["-110"])[0],
    }

    prediction = all_data_predict(row)
    return save_prediction_payload(prediction)








def incremental_features_build_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from build_incremental_features import build_features

    season = int(query.get("season", ["2026"])[0])
    phase = query.get("phase", ["regular"])[0]

    return build_features(season=season, phase=phase)


def incremental_features_cross_reference_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from build_incremental_features import cross_reference_player

    season = int(query.get("season", ["2026"])[0])
    player = query.get("player", [""])[0]
    kind = query.get("kind", ["batter"])[0]

    return cross_reference_player(player_name=player, season=season, kind=kind)


def incremental_stats_catchup_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from incremental_stats_collector import catchup_stats

    season = int(query.get("season", ["2026"])[0])
    start_date = query.get("start_date", [""])[0]
    end_date = query.get("end_date", [""])[0]
    force = query.get("force", ["0"])[0] in {"1", "true", "yes"}
    max_dates = int(query.get("max_dates", ["0"])[0])
    season_phase = query.get("season_phase", ["regular"])[0]

    return catchup_stats(
        season=season,
        start_date=start_date,
        end_date=end_date,
        force=force,
        max_dates=max_dates,
        season_phase=season_phase,
    )


def incremental_stats_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from incremental_stats_collector import status

    season = int(query.get("season", ["2026"])[0])
    return status(season)


def incremental_stats_lookup_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from incremental_stats_collector import lookup

    season = int(query.get("season", ["2026"])[0])
    q = query.get("q", [""])[0]
    kind = query.get("kind", ["all"])[0]
    limit = int(query.get("limit", ["20"])[0])

    return lookup(query=q, kind=kind, season=season, limit=limit)


def season_cache_backfill_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from season_stats_cache import backfill_played_games

    season = int(query.get("season", ["2026"])[0])
    start_date = query.get("start_date", [""])[0]
    end_date = query.get("end_date", [""])[0]
    force = query.get("force", ["0"])[0] in {"1", "true", "yes"}

    return backfill_played_games(season=season, start_date=start_date, end_date=end_date, force=force)


def season_cache_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from season_stats_cache import status

    season = int(query.get("season", ["2026"])[0])
    return status(season)


def season_cache_lookup_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from season_stats_cache import lookup

    season = int(query.get("season", ["2026"])[0])
    q = query.get("q", [""])[0]
    kind = query.get("kind", ["all"])[0]
    limit = int(query.get("limit", ["20"])[0])

    return lookup(query=q, kind=kind, season=season, limit=limit)




def weather_sync_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from weather_collector import collect_and_build

    season = int(query.get("season", ["2026"])[0])
    phase = query.get("phase", ["regular"])[0]
    force = query.get("force", ["0"])[0] in {"1", "true", "yes"}

    return collect_and_build(season=season, phase=phase, force=force)


def weather_build_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from weather_collector import build_weather_features

    season = int(query.get("season", ["2026"])[0])
    phase = query.get("phase", ["regular"])[0]

    return build_weather_features(season=season, phase=phase)




def odds_movement_sync_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from odds_movement import snapshot_and_build

    season = int(query.get("season", ["2026"])[0])
    date_label = query.get("date", [""])[0]
    market = query.get("market", [""])[0]

    return snapshot_and_build(date_label=date_label, market=market, season=season)


def odds_movement_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from pathlib import Path
    import json

    season = int(query.get("season", ["2026"])[0])
    path = Path("data/cache/odds_movement/status_%s.json" % season)

    if not path.exists():
        return {
            "season": season,
            "snapshotRows": 0,
            "movementRows": 0,
            "message": "No odds movement status yet. Run sync first.",
        }

    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))




def savant_sync_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from savant_features import sync_savant

    season = int(query.get("season", ["2026"])[0])
    start_date = query.get("start_date", [""])[0]
    end_date = query.get("end_date", [""])[0]
    force = query.get("force", ["0"])[0] in {"1", "true", "yes"}

    return sync_savant(season=season, start_date=start_date, end_date=end_date, force=force)


def savant_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from savant_features import status

    season = int(query.get("season", ["2026"])[0])
    return status(season)




def prediction_save_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from unified_prop_card import unified_prop_card
    from prediction_history import save_prediction

    row = {key: values[0] if values else "" for key, values in query.items()}
    card = unified_prop_card(row)
    return save_prediction(card)


def prediction_grade_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from prediction_history import grade_predictions

    season = int(query.get("season", ["2026"])[0])
    return grade_predictions(season)




def prediction_dashboard_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from prediction_history import prediction_dashboard

    season = int(query.get("season", ["2026"])[0])
    market = query.get("market", [""])[0]
    confidence = query.get("confidence", [""])[0]
    recommendation = query.get("recommendation", [""])[0]
    date = query.get("date", [""])[0]
    limit = int(query.get("limit", ["50"])[0])

    return prediction_dashboard(
        season=season,
        market=market,
        confidence=confidence,
        recommendation=recommendation,
        date=date,
        limit=limit,
    )



def stage3_line_comparison_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from stage3_betting_features import line_comparison_payload
    return line_comparison_payload(query)


def stage3_steam_alerts_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from stage3_betting_features import steam_alerts_payload
    return steam_alerts_payload(query)


def stage3_pnl_analytics_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from stage3_betting_features import pnl_analytics_payload
    return pnl_analytics_payload(query)


def prediction_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from prediction_history import status

    season = int(query.get("season", ["2026"])[0])
    return status(season)




def player_search_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from player_autofill import find_player

    season = int(query.get("season", ["2026"])[0])
    q = query.get("q", [""])[0]
    limit = int(query.get("limit", ["10"])[0])

    return {"players": find_player(season, q, limit)}








def model_performance_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from model_performance import performance_summary

    season = int(query.get("season", ["2026"])[0])
    return performance_summary(season)




def app_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = int(query.get("season", ["2026"])[0])

    playerboard = playerboard_health_payload({
        "season": [str(season)],
    })

    grading = grading_health_payload({
        "date": [playerboard.get("latestAvailableDate", "") or playerboard.get("date", "") or ""],
    })

    workflows = workflow_summaries_payload({})

    grading_summary = grading.get("summary") or {}
    workflow_summaries = workflows.get("summaries") or {}

    daily_health = workflow_summaries.get("dailyHealth") or {}
    daily_grading = workflow_summaries.get("dailyGrading") or {}
    weekly_repair = workflow_summaries.get("weeklyRepair") or {}

    warnings = []
    if not playerboard.get("ok"):
        warnings.append("Playerboard needs attention.")
    if not grading.get("ok"):
        warnings.append("Grading needs attention.")
    if not workflows.get("ok"):
        warnings.append("Workflow summaries need attention.")

    return {
        "ok": not warnings,
        "season": season,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "playerboard": {
            "ok": bool(playerboard.get("ok")),
            "date": playerboard.get("date") or playerboard.get("latestAvailableDate") or "",
            "latestAvailableDate": playerboard.get("latestAvailableDate") or "",
            "rowsLoaded": playerboard.get("rowsLoaded", 0),
            "totalRowsInFile": playerboard.get("totalRowsInFile", 0),
            "badShiftedRows": playerboard.get("badShiftedRows", 0),
            "missingMarketDisplayRows": playerboard.get("missingMarketDisplayRows", 0),
        },
        "grading": {
            "ok": bool(grading.get("ok")),
            "date": grading.get("date", ""),
            "backtestRowsForDate": grading_summary.get("backtestRowsForDate", 0),
            "gradedBacktestRowsForDate": grading_summary.get("gradedBacktestRowsForDate", 0),
            "mlRowsForDate": grading_summary.get("mlRowsForDate", 0),
            "gradedMlRowsForDate": grading_summary.get("gradedMlRowsForDate", 0),
        },
        "workflows": {
            "ok": bool(workflows.get("ok")),
            "dailyHealth": {
                "ok": bool(daily_health.get("ok")),
                "date": daily_health.get("date", ""),
                "checkedAt": daily_health.get("checkedAt", ""),
                "exists": bool(daily_health.get("exists")),
            },
            "dailyGrading": {
                "ok": bool(daily_grading.get("ok")),
                "date": daily_grading.get("date", ""),
                "checkedAt": daily_grading.get("checkedAt", ""),
                "exists": bool(daily_grading.get("exists")),
            },
            "weeklyRepair": {
                "ok": bool(weekly_repair.get("ok")),
                "date": weekly_repair.get("date", ""),
                "checkedAt": weekly_repair.get("checkedAt", ""),
                "exists": bool(weekly_repair.get("exists")),
            },
        },
    }

def playerboard_health_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from collections import Counter
    from playerboard import (
        PLAYERBOARD_FIELDS,
        playerboard_file,
        read_csv_rows,
        normalize_market,
        playerboard_schema_issue,
        playerboard_row_looks_shifted,
        clean,
    )

    season = int(query.get("season", ["2026"])[0])
    requested_date = query.get("date", [""])[0]
    market = query.get("market", [""])[0]
    target_market = normalize_market(market) if market else ""

    path = playerboard_file(season)
    rows = read_csv_rows(path)

    available_dates = sorted({
        clean(row.get("date"))
        for row in rows
        if clean(row.get("date"))
    })
    latest_available_date = available_dates[-1] if available_dates else ""

    # If no date is provided, default to the latest saved Playerboard date.
    date_label = requested_date or latest_available_date

    filtered = []
    for row in rows:
        if date_label and clean(row.get("date")) != date_label:
            continue
        if target_market and normalize_market(row.get("market")) != target_market:
            continue
        filtered.append(row)

    market_counts = Counter(normalize_market(row.get("market")) for row in filtered if clean(row.get("market")))

    missing_market_display = [
        row for row in filtered
        if not clean(row.get("marketDisplay"))
    ]

    bad_shifted_rows = [
        row for row in filtered
        if playerboard_row_looks_shifted(row)
    ]

    snapshots = sorted({
        clean(row.get("snapshotAt"))
        for row in filtered
        if clean(row.get("snapshotAt"))
    })

    latest_snapshot = snapshots[-1] if snapshots else ""

    schema_issue = playerboard_schema_issue(path, PLAYERBOARD_FIELDS)

    return {
        "season": season,
        "date": date_label,
        "requestedDate": requested_date,
        "latestAvailableDate": latest_available_date,
        "availableDates": available_dates[-30:],
        "usedLatestAvailableDate": bool(requested_date and requested_date != date_label and date_label == latest_available_date),
        "market": market,
        "file": str(path),
        "exists": path.exists(),
        "schemaVersion": "PLAYERBOARD_FIELDS_v2",
        "schemaOk": path.exists() and not schema_issue,
        "schemaIssue": schema_issue,
        "expectedColumnCount": len(PLAYERBOARD_FIELDS),
        "expectedColumns": PLAYERBOARD_FIELDS,
        "rowsLoaded": len(filtered),
        "totalRowsInFile": len(rows),
        "marketsPresent": dict(sorted(market_counts.items())),
        "missingMarketDisplayRows": len(missing_market_display),
        "badShiftedRows": len(bad_shifted_rows),
        "latestSnapshotAt": latest_snapshot,
        "snapshots": snapshots[-10:],
        "sampleBadRows": bad_shifted_rows[:5],
        "sampleMissingMarketDisplayRows": missing_market_display[:5],
        "ok": bool(path.exists() and not schema_issue and len(filtered) > 0 and not bad_shifted_rows),
    }


def playerboard_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from playerboard import build_playerboard, load_saved_playerboard

    season = int(query.get("season", ["2026"])[0])
    date_label = query.get("date", [""])[0]
    market = query.get("market", [""])[0]
    limit = int(query.get("limit", ["50"])[0])

    # UI/API loads should not append ML snapshots by default.
    # GitHub collector calls build_playerboard(..., save=True) directly.
    save = query.get("save", ["0"])[0] in {"1", "true", "True", "yes"}
    refresh = query.get("refresh", ["0"])[0] in {"1", "true", "True", "yes"}
    build_if_missing = query.get("buildIfMissing", ["0"])[0] in {"1", "true", "True", "yes"}

    if not save and not refresh:
        cached = load_saved_playerboard(season=season, date_label=date_label, market=market, limit=limit)
        if cached.get("cacheHit") or not build_if_missing:
            return cached

    return build_playerboard(season=season, date_label=date_label, market=market, limit=limit, save=save)


def player_profile_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from player_profile import get_profile

    season = int(query.get("season", ["2026"])[0])
    date_label = query.get("date", [""])[0]
    player = query.get("player", [""])[0]

    return get_profile(season, date_label, player)


def player_autofill_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from player_autofill import autofill_player

    season = int(query.get("season", ["2026"])[0])
    date_label = query.get("date", [""])[0]
    player = query.get("player", [""])[0]
    role = query.get("role", ["auto"])[0]

    return autofill_player(season, date_label, player, role)


def unified_prop_card_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from unified_prop_card import unified_prop_card

    row = {
        "season": query.get("season", ["2026"])[0],
        "date": query.get("date", [""])[0],
        "market": query.get("market", ["batter_hits"])[0],
        "player": query.get("player", [""])[0],
        "team": query.get("team", [""])[0],
        "opponent": query.get("opponent", [""])[0],
        "pitcher": query.get("pitcher", [""])[0],
        "line": query.get("line", ["0.5"])[0],
        "american_odds": query.get("american_odds", ["-110"])[0],
    }

    return unified_prop_card(row)


def all_data_prop_query_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from unified_prop_context import all_data_predict

    row = {
        "date": query.get("date", [""])[0],
        "market": query.get("market", ["batter_hits"])[0],
        "player": query.get("player", [""])[0],
        "team": query.get("team", [""])[0],
        "opponent": query.get("opponent", [""])[0],
        "pitcher": query.get("pitcher", [""])[0],
        "line": query.get("line", ["0.5"])[0],
        "american_odds": query.get("american_odds", ["-110"])[0],
    }

    return all_data_predict(row)


def batter_pitcher_samples_payload() -> dict[str, Any]:
    from unified_prop_context import build_batter_pitcher_samples

    return build_batter_pitcher_samples()


def prop_ml_prediction_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from ml_prop_model import predict_from_row as prop_predict_from_row

    market = prop_ml_query_value(query, "market", "pitcher_strikeouts")
    player = prop_ml_query_value(query, "player")
    team = prop_ml_query_value(query, "team")
    opponent = prop_ml_query_value(query, "opponent")
    pitcher = prop_ml_query_value(query, "pitcher")

    line = prop_ml_query_float(query, "line", 0.5)
    american_odds = prop_ml_query_float(query, "american_odds", -110)

    row = {
        "market": market,
        "player": player,
        "team": team,
        "opponent": opponent,
        "pitcher": pitcher,
        "line": line,
        "american_odds": american_odds,
        "recent_games": prop_ml_query_float(query, "recent_games", 0),
        "recent_rate": prop_ml_query_float(query, "recent_rate", 0),
        "season_rate": prop_ml_query_float(query, "season_rate", 0),
        "rolling_avg_5": prop_ml_query_float(query, "rolling_avg_5", 0),
        "rolling_avg_10": prop_ml_query_float(query, "rolling_avg_10", 0),
        "rolling_avg_15": prop_ml_query_float(query, "rolling_avg_15", 0),
        "rolling_total_bases_10": prop_ml_query_float(query, "rolling_total_bases_10", 0),
        "rolling_hr_rate_15": prop_ml_query_float(query, "rolling_hr_rate_15", 0),
        "rolling_k_rate_10": prop_ml_query_float(query, "rolling_k_rate_10", 0),
        "opponent_rate": prop_ml_query_float(query, "opponent_rate", 0),
        "pitcher_k_rate": prop_ml_query_float(query, "pitcher_k_rate", 0),
        "pitcher_walk_rate": prop_ml_query_float(query, "pitcher_walk_rate", 0),
        "pitcher_hr_rate": prop_ml_query_float(query, "pitcher_hr_rate", 0),
        "team_k_rate": prop_ml_query_float(query, "team_k_rate", 0),
        "team_walk_rate": prop_ml_query_float(query, "team_walk_rate", 0),
        "batter_k_rate": prop_ml_query_float(query, "batter_k_rate", 0),
        "batter_walk_rate": prop_ml_query_float(query, "batter_walk_rate", 0),
        "barrel_rate": prop_ml_query_float(query, "barrel_rate", 0),
        "hard_hit_rate": prop_ml_query_float(query, "hard_hit_rate", 0),
        "xwoba": prop_ml_query_float(query, "xwoba", 0),
        "xba": prop_ml_query_float(query, "xba", 0),
        "xslg": prop_ml_query_float(query, "xslg", 0),
        "park_factor": prop_ml_query_float(query, "park_factor", 1.0),
        "hit_factor": prop_ml_query_float(query, "hit_factor", 1.0),
        "hr_factor": prop_ml_query_float(query, "hr_factor", 1.0),
        "k_factor": prop_ml_query_float(query, "k_factor", 1.0),
        "temperature": prop_ml_query_float(query, "temperature", 0),
        "wind_mph": prop_ml_query_float(query, "wind_mph", 0),
        "throws": prop_ml_query_value(query, "throws"),
        "bats": prop_ml_query_value(query, "bats"),
        "venue": prop_ml_query_value(query, "venue"),
        "roof": prop_ml_query_value(query, "roof"),
    }

    prediction = prop_predict_from_row(row, market=market).to_dict()

    probability = float(prediction.get("probability", 0))
    implied = float(prediction.get("impliedProbability", 0))
    edge = float(prediction.get("edge", 0))
    expected_value = float(prediction.get("expectedValue", 0))

    return {
        **prediction,
        "market": market,
        "player": player,
        "team": team,
        "opponent": opponent,
        "pitcher": pitcher,
        "line": line,
        "americanOdds": american_odds,
        "probabilityPercent": round(probability * 100, 2),
        "impliedProbabilityPercent": round(implied * 100, 2),
        "edgePercent": round(edge * 100, 2),
        "expectedValuePercent": round(expected_value * 100, 2),
        "recommendation": "positive edge" if edge > 0 else "negative edge",
    }


from ml_prop_model import metadata_path_for_model, model_path_for_market, predict_from_row, train_model
import inspect

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "batting.json"
OPPONENT_FILE = DATA_DIR / "opponents.json"
GAME_LOG_FILE = DATA_DIR / "game_logs.json"
PITCHING_GAME_LOG_FILE = DATA_DIR / "pitching_game_logs.json"
TEAM_GAME_LOG_FILE = DATA_DIR / "team_game_logs.json"
TEAM_BATTING_FILE = DATA_DIR / "team_batting.json"
BASERUNNING_FILE = DATA_DIR / "baserunning.json"
PITCHING_FILE = DATA_DIR / "pitching.json"
BATTING_AGAINST_FILE = DATA_DIR / "batting_against.json"
TEAM_BATTING_AGAINST_FILE = DATA_DIR / "team_batting_against.json"
TEAM_ADVANCED_PITCHING_FILE = DATA_DIR / "team_advanced_pitching.json"
PLAYER_ADVANCED_PITCHING_FILE = DATA_DIR / "player_advanced_pitching.json"
TEAM_STANDARD_PITCHING_FILE = DATA_DIR / "team_standard_pitching.json"
BATTER_PITCHER_ADVANCED_FILE = DATA_DIR / "batter_pitcher_advanced.json"
STATCAST_QUALITY_FILE = DATA_DIR / "statcast_quality.json"
HANDEDNESS_SPLITS_FILE = DATA_DIR / "handedness_splits.json"
ROLLING_FORM_FILE = DATA_DIR / "rolling_form.json"
PITCH_ARSENAL_FILE = DATA_DIR / "pitch_arsenal.json"
GAME_CONTEXT_FILE = DATA_DIR / "game_context.json"
BALLPARK_CONTEXT_FILE = DATA_DIR / "ballpark_context.json"
DATASET_META_FILE = DATA_DIR / "datasets.json"
DATASET_SOURCE_FILE = DATA_DIR / "dataset_sources.json"
DEFAULT_CSV = Path(r"C:\Users\RevLe\Downloads\batting.csv")
GITHUB_API_BASE = "https://api.github.com"
ESPN_MLB_API_BASE = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"
BASEBALL_SAVANT_SEARCH_CSV = "https://baseballsavant.mlb.com/statcast_search/csv"
BALLPARKPAL_API_BASE = "https://www.ballparkpal.com/api"
DATASET_AUTO_REFRESH_SECONDS = 8 * 60 * 60
DATASET_REFRESH_LOCK = threading.RLock()

ENV_FILE = ROOT / ".env"


def load_local_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env_file()

PROPLINE_API_KEY = os.environ.get("PROPLINE_API_KEY", "")


TEAM_NAMES = {
    "ARI": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CHW": "Chicago White Sox",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KCR": "Kansas City Royals",
    "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "ATH": "Athletics",
    "OAK": "Oakland Athletics",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SDP": "San Diego Padres",
    "SD": "San Diego Padres",
    "SEA": "Seattle Mariners",
    "SFG": "San Francisco Giants",
    "SF": "San Francisco Giants",
    "STL": "St. Louis Cardinals",
    "TBR": "Tampa Bay Rays",
    "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSN": "Washington Nationals",
    "WSH": "Washington Nationals",
}


@dataclass
class Player:
    player: str
    team: str
    league: str
    games: int
    plate_appearances: int
    at_bats: int
    hits: int
    doubles: int
    triples: int
    home_runs: int
    walks: int
    strikeouts: int
    batting_average: float
    on_base: float
    slugging: float
    ops: float
    total_bases: int
    player_id: str


def clean_name(value: str) -> str:
    return value.replace("*", "").replace("#", "").strip()


def is_summary_name(value: str) -> bool:
    text = clean_name(value).lower()
    return text in {"mlb average", "league average", "lg average"} or text.endswith(" average")


def to_int(value: Any, default: int = 0) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric text to float, returning default for missing/invalid values.
    
    This helper is for aggregation/reporting where default=0.0 is intentional.
    Do not use it for ML feature extraction when missingness must stay explicit;
    use ml_prop_model.to_float() or a nullable parser instead.
    """
    text = str(value or "").strip()
    if not text:
        return default
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100
        return float(text)
    except ValueError:
        return default


def to_baseball_innings(value: Any, default: float = 0.0) -> float:
    text = str(value or "").strip()
    if not text:
        return default
    if "." in text:
        whole, outs = text.split(".", 1)
        if outs[:1] in {"0", "1", "2"}:
            return to_int(whole) + to_int(outs[:1]) / 3
    return to_float(text, default)


def to_rate(value: Any, default: float = 0.0) -> float:
    rate = to_float(value, default)
    return rate / 100 if rate > 1 else rate


def normalize_rows(raw: str) -> list[dict[str, str]]:
    rows = list(csv.reader(io.StringIO(raw)))
    if rows and len(rows[0]) == 1 and "," in rows[0][0]:
        rows = [next(csv.reader([row[0]])) for row in rows if row]
    if not rows:
        return []

    header_names = {
        "player",
        "name",
        "pitcher",
        "team",
        "tm",
        "opponent",
        "opp",
        "g",
        "pa",
        "ab",
        "h",
        "ip",
        "era",
        "whip",
        "ba",
        "obp",
        "slg",
        "ops",
        "k%",
        "so%",
        "bb%",
    }
    header_index = 0
    best_score = -1
    for index, row in enumerate(rows[:5]):
        score = sum(1 for column in row if column.strip().strip('"').lower() in header_names)
        if score > best_score:
            best_score = score
            header_index = index

    header = [column.strip().strip('"') for column in rows[header_index]]
    normalized: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        if not row or len(row) < 2:
            continue
        values = row + [""] * max(0, len(header) - len(row))
        record = {header[index]: values[index].strip().strip('"') for index in range(len(header))}
        if any(record.values()):
            normalized.append(record)
    return normalized


class FirstHtmlTableParser(HTMLParser):
    def __init__(self, table_id: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.table_id = table_id
        self.rows: list[list[str]] = []
        self._in_table = False
        self._done = False
        self._table_depth = 0
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        tag = tag.lower()
        if tag == "table":
            if not self._in_table:
                attrs_dict = {name.lower(): value or "" for name, value in attrs}
                if self.table_id and attrs_dict.get("id") != self.table_id:
                    return
                self._in_table = True
            self._table_depth += 1
            return
        if not self._in_table:
            return
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._in_table and self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        tag = tag.lower()
        if not self._in_table:
            return
        if tag in {"td", "th"} and self._current_cell is not None:
            text = " ".join("".join(self._current_cell).split())
            if self._current_row is not None:
                self._current_row.append(text)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._in_table = False
                self._done = True


def html_table_to_csv(raw: str, table_id: str = "") -> str:
    parser = FirstHtmlTableParser(table_id)
    parser.feed(raw)
    rows = parser.rows
    if not rows:
        if table_id:
            raise ValueError(f"No HTML table named {table_id} found at this URL.")
        raise ValueError("No HTML table rows found at this URL.")
    width = max(len(row) for row in rows)
    output = io.StringIO()
    writer = csv.writer(output)
    for row in rows:
        writer.writerow(row + [""] * (width - len(row)))
    return output.getvalue()


def baseball_reference_table_ids(parsed_url: Any) -> list[str]:
    fragment = parsed_url.fragment.strip()
    table_ids: list[str] = []
    if fragment:
        table_ids.append(fragment)
        if fragment.startswith("all_"):
            table_ids.append(fragment.removeprefix("all_"))
    if "standard-pitching" in parsed_url.path:
        table_ids.extend(["players_standard_pitching", "teams_standard_pitching"])
    return list(dict.fromkeys(table_ids))


def html_table_to_csv_by_id(raw: str, table_ids: list[str]) -> str:
    errors = []
    sources = [raw]
    sources.extend(comment for comment in re.findall(r"<!--(.*?)-->", raw, flags=re.DOTALL) if "<table" in comment)
    for table_id in table_ids:
        for source in sources:
            try:
                return html_table_to_csv(source, table_id)
            except ValueError as error:
                errors.append(str(error))
    if table_ids:
        raise ValueError(f"No matching HTML table found. Tried: {', '.join(table_ids)}.")
    return html_table_to_csv(raw)


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def dataset_url_allowed_hosts() -> list[str]:
    raw = os.environ.get("DATASET_URL_ALLOWED_HOSTS", "").strip()
    if not raw:
        return []
    return [
        item.strip().lower().removeprefix("*.").lstrip(".")
        for item in raw.split(",")
        if item.strip()
    ]


def hostname_matches_allowed(hostname: str, allowed_host: str) -> bool:
    hostname = hostname.lower().strip(".")
    allowed_host = allowed_host.lower().strip(".")
    return hostname == allowed_host or hostname.endswith(f".{allowed_host}")


def validate_dataset_url_target(parsed: Any) -> None:
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise ValueError("Dataset URL must include a host name.")
    if parsed.username or parsed.password:
        raise ValueError("Dataset URL must not include embedded credentials.")

    allowed_hosts = dataset_url_allowed_hosts()
    if allowed_hosts and not any(hostname_matches_allowed(hostname, allowed) for allowed in allowed_hosts):
        raise ValueError("Dataset URL host is not in DATASET_URL_ALLOWED_HOSTS.")

    if env_flag("DATASET_URL_ALLOW_PRIVATE"):
        return

    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise ValueError("Dataset URL host resolves to a private or local network address.")

    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError(f"Could not resolve dataset URL host: {hostname}") from error

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("Dataset URL host resolves to a private or local network address.")


class DatasetUrlRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        parsed = urlparse(newurl)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Dataset URL redirects must use http:// or https://.")
        validate_dataset_url_target(parsed)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_dataset_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Dataset URL must start with http:// or https://.")
    validate_dataset_url_target(parsed)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/csv,text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5",
            "User-Agent": "baseball-prop-predictor",
        },
    )
    try:
        opener = urllib.request.build_opener(DatasetUrlRedirectHandler())
        with opener.open(request, timeout=20) as response:
            validate_dataset_url_target(urlparse(response.geturl()))
            content_type = response.headers.get("Content-Type", "")
            raw_bytes = response.read(12_000_000)
    except urllib.error.URLError as error:
        raise ValueError(f"Could not fetch dataset URL: {error.reason}") from error

    raw = raw_bytes.decode("utf-8-sig", errors="replace")
    filename = Path(parsed.path).name or parsed.netloc
    looks_html = "html" in content_type.lower() or raw.lstrip().lower().startswith(("<!doctype html", "<html"))
    if looks_html:
        if parsed.netloc.endswith("baseball-reference.com"):
            table_ids = baseball_reference_table_ids(parsed)
            if table_ids:
                return html_table_to_csv_by_id(raw, table_ids), f"{filename or parsed.netloc}.html"
        return html_table_to_csv(raw), f"{filename or parsed.netloc}.html"
    return raw, filename or "remote-dataset.csv"


def first_value(row: dict[str, str], names: list[str]) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for name in names:
        if name in row and row[name] != "":
            return row[name]
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def normalize_team_code(value: str) -> str:
    text = value.strip().upper()
    if text in TEAM_NAMES:
        return text
    for code, name in TEAM_NAMES.items():
        if text == name.upper():
            return code
    return text[:3]


def team_from_dataset_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query_team = parse_qs(parsed.query).get("team", [""])[0]
    if query_team:
        return normalize_team_code(query_team)
    return ""


def record_key(record: dict[str, Any], fields: list[str]) -> str:
    parts = [str(record.get(field, "")).strip().lower() for field in fields]
    return "|".join(parts)


def populated_record_key(record: dict[str, Any], fields: list[str]) -> str:
    parts = [str(record.get(field, "")).strip().lower() for field in fields]
    return "|".join(parts) if all(parts) else ""


def looks_like_standard_pitching_record(record: dict[str, Any]) -> bool:
    if not record.get("pitcher") or is_summary_name(str(record.get("pitcher", ""))):
        return False
    return any(
        [
            to_float(record.get("innings")) > 0,
            to_int(record.get("gamesStarted")) > 0,
            to_float(record.get("era")) > 0,
            to_float(record.get("fip")) > 0,
            to_float(record.get("whip")) > 0,
            to_float(record.get("hitsPerNine")) > 0,
        ]
    )


def looks_like_pitcher_option(record: dict[str, Any]) -> bool:
    if not record.get("pitcher") or is_summary_name(str(record.get("pitcher", ""))):
        return False
    return any(
        [
            looks_like_standard_pitching_record(record),
            to_float(record.get("strikeoutRate")) > 0,
            to_float(record.get("walkRate")) > 0,
            to_float(record.get("kMinusBbRate")) > 0,
            to_float(record.get("battingAverageAllowed")) > 0,
            to_float(record.get("opsAllowed")) > 0,
            to_float(record.get("sluggingAllowed")) > 0,
        ]
    )


def valid_batter_game_log_sample(record: dict[str, Any]) -> bool:
    games = max(to_int(record.get("games"), 1), 1)
    at_bats = to_int(record.get("atBats"))
    hits = to_int(record.get("hits"))
    plate_appearances = to_int(record.get("plateAppearances"))
    if not any([at_bats, hits, plate_appearances]):
        return False
    # A one-game player log cannot have team-sized volume. This catches team batting
    # game logs that were accidentally loaded as individual batter logs.
    return at_bats / games <= 7.5 and hits / games <= 5.0 and plate_appearances / games <= 8.0


def merge_records(path: Path, new_records: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    existing = load_json_file(path, [])
    merged = {record_key(record, key_fields): record for record in existing if record_key(record, key_fields).strip("|")}
    for record in new_records:
        key = record_key(record, key_fields)
        if key.strip("|"):
            name_team_key = populated_record_key(record, ["pitcher", "team"]) or populated_record_key(record, ["player", "team"])
            if name_team_key:
                for existing_key, existing_record in list(merged.items()):
                    existing_name_team_key = populated_record_key(existing_record, ["pitcher", "team"]) or populated_record_key(existing_record, ["player", "team"])
                    if existing_name_team_key == name_team_key and existing_key != key:
                        record = {**existing_record, **record}
                        del merged[existing_key]
            merged[key] = {**merged.get(key, {}), **record}
    records = list(merged.values())
    save_json_file(path, records)
    return records


def parse_players(raw: str) -> list[Player]:
    players: list[Player] = []
    for row in normalize_rows(raw):
        player_name = clean_name(first_value(row, ["Player", "Name", "Batter"]))
        if not player_name or is_summary_name(player_name):
            continue
        at_bats = to_int(first_value(row, ["AB"]))
        hits = to_int(first_value(row, ["H", "Hits"]))
        batting_average = to_float(first_value(row, ["BA", "AVG"]), hits / at_bats if at_bats else 0.0)
        doubles = to_int(first_value(row, ["2B", "Doubles"]))
        triples = to_int(first_value(row, ["3B", "Triples"]))
        home_runs = to_int(first_value(row, ["HR", "Home Runs"]))
        listed_total_bases = to_int(first_value(row, ["TB", "Total Bases"]))
        singles = max(hits - doubles - triples - home_runs, 0)
        total_bases = listed_total_bases or singles + doubles * 2 + triples * 3 + home_runs * 4
        players.append(
            Player(
                player=player_name,
                team=normalize_team_code(first_value(row, ["Team", "Tm"])),
                league=first_value(row, ["Lg", "League"]).strip(),
                games=to_int(first_value(row, ["G", "Games"])),
                plate_appearances=to_int(first_value(row, ["PA", "Plate Appearances"])),
                at_bats=at_bats,
                hits=hits,
                doubles=doubles,
                triples=triples,
                home_runs=home_runs,
                walks=to_int(first_value(row, ["BB", "Walks"])),
                strikeouts=to_int(first_value(row, ["SO", "K", "Strikeouts"])),
                batting_average=batting_average,
                on_base=to_float(first_value(row, ["OBP"])),
                slugging=to_float(first_value(row, ["SLG"])),
                ops=to_float(first_value(row, ["OPS"])),
                total_bases=total_bases,
                player_id=first_value(row, ["Player-additional", "Name-additional", "player_id", "PlayerID", "ID"]).strip(),
            )
        )
    return players


def parse_opponents(raw: str) -> list[dict[str, Any]]:
    opponents: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        team = normalize_team_code(first_value(row, ["Team", "Tm", "Squad", "Opponent", "Opp"]))
        if not team:
            continue
        games = to_int(first_value(row, ["G", "Games"]))
        innings = to_float(first_value(row, ["IP", "Innings", "Innings Pitched"]))
        hits_allowed = to_int(first_value(row, ["H", "HA", "Hits", "Hits Allowed", "H_allowed"]))
        at_bats = to_int(first_value(row, ["AB", "BFP", "BF", "TBF", "PA"]))
        batting_average_allowed = to_float(
            first_value(row, ["BA", "BAA", "AVG", "AVG Allowed", "Batting Average Allowed"]),
            hits_allowed / at_bats if at_bats else 0.0,
        )
        whip = to_float(first_value(row, ["WHIP"]))
        era = to_float(first_value(row, ["ERA"]))
        hits_per_game = hits_allowed / games if games else 0.0
        hits_per_nine = hits_allowed * 9 / innings if innings else 0.0
        if not any([batting_average_allowed, hits_per_game, hits_per_nine, whip, era]):
            continue
        opponents.append(
            {
                "team": team,
                "name": TEAM_NAMES.get(team, team),
                "games": games,
                "hitsAllowed": hits_allowed,
                "battingAverageAllowed": batting_average_allowed,
                "hitsPerGame": hits_per_game,
                "hitsPerNine": hits_per_nine,
                "whip": whip,
                "era": era,
            }
        )
    return opponents


def parse_game_logs(raw: str) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in normalize_rows(raw):
        player = clean_name(first_value(row, ["Player", "Name", "Batter"]))
        opponent = normalize_team_code(first_value(row, ["Opp", "Opponent", "Vs", "Against"]))
        if not player or not opponent:
            continue
        player_id = first_value(row, ["Player-additional", "Name-additional", "player_id", "PlayerID", "ID"])
        at_bats = to_int(first_value(row, ["AB", "At Bats", "AtBats"]))
        hits = to_int(first_value(row, ["H", "Hits"]))
        plate_appearances = to_int(first_value(row, ["PA", "Plate Appearances"]))
        if at_bats <= 0 and hits <= 0 and plate_appearances <= 0:
            continue
        entry = {
            "date": first_value(row, ["Date", "Game Date", "GmDate"]),
            "opponent": opponent,
            "plateAppearances": plate_appearances,
            "atBats": at_bats,
            "hits": hits,
            "homeRuns": to_int(first_value(row, ["HR", "Home Runs"])),
            "walks": to_int(first_value(row, ["BB", "Walks"])),
            "strikeouts": to_int(first_value(row, ["SO", "K", "Strikeouts"])),
            "totalBases": to_int(first_value(row, ["TB", "Total Bases"]), hits),
        }
        if not valid_batter_game_log_sample({**entry, "games": 1}):
            continue
        key = (player_id, player.lower(), opponent)
        bucket = buckets.setdefault(
            key,
            {
                "playerId": player_id,
                "player": player,
                "opponent": opponent,
                "games": 0,
                "plateAppearances": 0,
                "atBats": 0,
                "hits": 0,
                "homeRuns": 0,
                "walks": 0,
                "strikeouts": 0,
                "totalBases": 0,
                "entries": [],
            },
        )
        bucket["games"] += 1
        bucket["plateAppearances"] += plate_appearances
        bucket["atBats"] += at_bats
        bucket["hits"] += hits
        bucket["homeRuns"] += entry["homeRuns"]
        bucket["walks"] += entry["walks"]
        bucket["strikeouts"] += entry["strikeouts"]
        bucket["totalBases"] += entry["totalBases"]
        bucket["entries"].append(entry)
    logs = []
    for bucket in buckets.values():
        bucket["battingAverage"] = bucket["hits"] / bucket["atBats"] if bucket["atBats"] else 0.0
        bucket["slugging"] = bucket["totalBases"] / bucket["atBats"] if bucket["atBats"] else 0.0
        logs.append(bucket)
    return logs


def parse_team_game_logs(raw: str, team_hint: str = "") -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    team = normalize_team_code(team_hint)
    for row in normalize_rows(raw):
        opponent = normalize_team_code(first_value(row, ["Opp", "Opponent", "Vs", "Against"]))
        date = first_value(row, ["Date", "Game Date", "GmDate"])
        if not opponent or not date:
            continue
        row_team = normalize_team_code(first_value(row, ["Team", "Tm", "Squad"]))
        batting_team = team or row_team
        if not batting_team:
            continue
        result = first_value(row, ["Rslt", "Result", "W/L", "WL"]).strip().upper()
        result_code = result[:1] if result else ""
        if result_code not in {"W", "L", "T"}:
            result_code = ""
        runs_scored = to_int(first_value(row, ["RS", "R", "Runs", "Runs Scored"]))
        runs_allowed = to_int(first_value(row, ["RA", "Runs Allowed"]))
        plate_appearances = to_int(first_value(row, ["PA", "Plate Appearances"]))
        at_bats = to_int(first_value(row, ["AB", "At Bats", "AtBats"]))
        hits = to_int(first_value(row, ["H", "Hits"]))
        total_bases = to_int(first_value(row, ["TB", "Total Bases"]))
        if not total_bases and hits:
            doubles = to_int(first_value(row, ["2B", "Doubles"]))
            triples = to_int(first_value(row, ["3B", "Triples"]))
            home_runs = to_int(first_value(row, ["HR", "Home Runs"]))
            singles = max(hits - doubles - triples - home_runs, 0)
            total_bases = singles + doubles * 2 + triples * 3 + home_runs * 4
        else:
            doubles = to_int(first_value(row, ["2B", "Doubles"]))
            triples = to_int(first_value(row, ["3B", "Triples"]))
            home_runs = to_int(first_value(row, ["HR", "Home Runs"]))
        if not any([plate_appearances, at_bats, hits, runs_scored, runs_allowed]):
            continue
        logs.append(
            {
                "team": batting_team,
                "name": TEAM_NAMES.get(batting_team, batting_team),
                "opponent": opponent,
                "opponentName": TEAM_NAMES.get(opponent, opponent),
                "date": date,
                "gameNumber": to_int(first_value(row, ["Gtm", "Game", "Rk"])),
                "homeAway": "away" if first_value(row, ["", "Home/Away", "HA"]).strip() == "@" else "home",
                "result": result_code,
                "win": result_code == "W",
                "loss": result_code == "L",
                "runsScored": runs_scored,
                "runsAllowed": runs_allowed,
                "innings": to_float(first_value(row, ["Inn", "Innings"]), 9.0),
                "plateAppearances": plate_appearances,
                "atBats": at_bats,
                "hits": hits,
                "doubles": doubles,
                "triples": triples,
                "homeRuns": home_runs,
                "walks": to_int(first_value(row, ["BB", "Walks"])),
                "strikeouts": to_int(first_value(row, ["SO", "K", "Strikeouts"])),
                "battingAverage": to_float(first_value(row, ["BA", "AVG"]), hits / at_bats if at_bats else 0.0),
                "onBase": to_float(first_value(row, ["OBP"])),
                "slugging": to_float(first_value(row, ["SLG"])),
                "ops": to_float(first_value(row, ["OPS"])),
                "totalBases": total_bases,
                "leftOnBase": to_int(first_value(row, ["LOB"])),
                "opposingPitcher": clean_name(first_value(row, ["Player", "Opp Starter", "Starter", "Pitcher"])),
                "opposingPitcherThrows": first_value(row, ["T", "Throws"]).strip(),
                "opposingPitcherGameScore": to_int(first_value(row, ["GmSc", "Game Score"])),
            }
        )
    return logs


def normalize_factor(value: Any, default: float = 1.0) -> float:
    text = str(value or "").strip()
    if not text:
        return default
    if text.endswith("%"):
        numeric = to_float(text[:-1])
        return 1 + numeric / 100 if abs(numeric) > 0.25 else 1 + numeric
    numeric = to_float(text, default)
    if numeric > 10:
        return numeric / 100
    if 0.5 <= numeric <= 1.5:
        return numeric
    if -50 <= numeric <= 50:
        return 1 + numeric / 100
    return default


def parse_ballpark_context(raw: str) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        home = normalize_team_code(first_value(row, ["Home Team", "Home", "homeTeam", "home_team", "Team"]))
        away = normalize_team_code(first_value(row, ["Away Team", "Away", "awayTeam", "away_team", "Opponent", "Opp"]))
        venue = first_value(row, ["Venue", "Ballpark", "Park", "Stadium", "venueName", "parkName"])
        date = first_value(row, ["Date", "Game Date", "gameDate", "date"])
        if not any([home, away, venue]):
            continue
        park_factor = normalize_factor(first_value(row, ["Park Factor", "ParkFactor", "Run Factor", "runFactor", "runsFactor"]), 1.0)
        hr_factor = normalize_factor(first_value(row, ["HR Factor", "Home Run Factor", "HR Adjustment", "hrFactor", "homeRunFactor"]), park_factor)
        hit_factor = normalize_factor(first_value(row, ["Hit Factor", "Hits Factor", "1B Factor", "BA Factor", "hitFactor"]), park_factor)
        context = {
            "source": first_value(row, ["Source"]) or "Imported ballpark context",
            "date": date,
            "gameId": first_value(row, ["Game ID", "GameId", "gamePk", "eventId"]),
            "game": first_value(row, ["Game", "Matchup"]) or f"{away or '--'} @ {home or '--'}",
            "venue": venue,
            "city": first_value(row, ["City"]),
            "homeTeam": home,
            "awayTeam": away,
            "temperature": to_float(first_value(row, ["Temperature", "Temp", "temperature", "tempF"])),
            "windMph": to_float(first_value(row, ["Wind MPH", "Wind Speed", "Wind", "windMph", "windSpeed"])),
            "windDirection": first_value(row, ["Wind Direction", "Wind Dir", "windDirection", "wind_dir"]).lower(),
            "roof": first_value(row, ["Roof", "Roof Status", "roofStatus", "roof"]).lower(),
            "weather": first_value(row, ["Weather", "Condition", "weather", "condition"]),
            "parkFactor": round(park_factor, 3),
            "homeRunFactor": round(hr_factor, 3),
            "hitFactor": round(hit_factor, 3),
            "runFactor": round(park_factor, 3),
            "notes": first_value(row, ["Notes", "Description"]),
        }
        contexts.append(context)
    return contexts


def parse_pitching_game_logs(raw: str) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in normalize_rows(raw):
        pitcher = clean_name(first_value(row, ["Pitcher", "Player", "Name"]))
        opponent = normalize_team_code(first_value(row, ["Opp", "Opponent", "Vs", "Against"]))
        if not pitcher or not opponent:
            continue
        pitcher_id = first_value(row, ["Player-additional", "Name-additional", "pitcher_id", "player_id", "PlayerID", "ID"])
        team = normalize_team_code(first_value(row, ["Team", "Tm"]))
        innings = to_float(first_value(row, ["IP", "Innings"]))
        hits_allowed = to_int(first_value(row, ["H", "HA", "Hits", "Hits Allowed"]))
        walks = to_int(first_value(row, ["BB", "Walks"]))
        strikeouts = to_int(first_value(row, ["SO", "K", "Strikeouts"]))
        batters_faced = to_int(first_value(row, ["BF", "BFP", "TBF", "PA"]))
        earned_runs = to_int(first_value(row, ["ER", "Earned Runs"]))
        if not any([innings, hits_allowed, walks, strikeouts, batters_faced, earned_runs]):
            continue
        key = (pitcher_id, pitcher.lower(), opponent)
        bucket = buckets.setdefault(
            key,
            {
                "pitcherId": pitcher_id,
                "pitcher": pitcher,
                "team": team,
                "opponent": opponent,
                "games": 0,
                "gamesStarted": 0,
                "innings": 0.0,
                "hitsAllowed": 0,
                "runsAllowed": 0,
                "earnedRuns": 0,
                "homeRunsAllowed": 0,
                "walks": 0,
                "strikeouts": 0,
                "battersFaced": 0,
            },
        )
        bucket["games"] += 1
        bucket["gamesStarted"] += to_int(first_value(row, ["GS", "Start", "Started"]), 1 if innings >= 2.0 else 0)
        bucket["innings"] += innings
        bucket["hitsAllowed"] += hits_allowed
        bucket["runsAllowed"] += to_int(first_value(row, ["R", "Runs"]))
        bucket["earnedRuns"] += earned_runs
        bucket["homeRunsAllowed"] += to_int(first_value(row, ["HR", "Home Runs"]))
        bucket["walks"] += walks
        bucket["strikeouts"] += strikeouts
        bucket["battersFaced"] += batters_faced

    logs = []
    for bucket in buckets.values():
        innings = bucket["innings"]
        batters_faced = bucket["battersFaced"]
        bucket["era"] = bucket["earnedRuns"] * 9 / innings if innings else 0.0
        bucket["whip"] = (bucket["walks"] + bucket["hitsAllowed"]) / innings if innings else 0.0
        bucket["hitsPerNine"] = bucket["hitsAllowed"] * 9 / innings if innings else 0.0
        bucket["strikeoutRate"] = bucket["strikeouts"] / batters_faced if batters_faced else 0.0
        logs.append(bucket)
    return logs


def parse_team_batting(raw: str) -> list[dict[str, Any]]:
    teams: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        team = normalize_team_code(first_value(row, ["Team", "Tm", "Squad"]))
        if not team or team in {"LG", "MLB"}:
            continue
        at_bats = to_int(first_value(row, ["AB"]))
        hits = to_int(first_value(row, ["H"]))
        teams.append(
            {
                "team": team,
                "name": TEAM_NAMES.get(team, team),
                "games": to_int(first_value(row, ["G", "Games"])),
                "plateAppearances": to_int(first_value(row, ["PA"])),
                "atBats": at_bats,
                "runs": to_int(first_value(row, ["R"])),
                "hits": hits,
                "homeRuns": to_int(first_value(row, ["HR"])),
                "walks": to_int(first_value(row, ["BB"])),
                "strikeouts": to_int(first_value(row, ["SO"])),
                "battingAverage": to_float(first_value(row, ["BA", "AVG"]), hits / at_bats if at_bats else 0.0),
                "onBase": to_float(first_value(row, ["OBP"])),
                "slugging": to_float(first_value(row, ["SLG"])),
                "ops": to_float(first_value(row, ["OPS"])),
                "runsPerGame": to_float(first_value(row, ["R/G", "RPG"])),
            }
        )
    return [team for team in teams if team["team"]]


def parse_baserunning(raw: str) -> list[dict[str, Any]]:
    runners: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        player = clean_name(first_value(row, ["Player", "Name"]))
        if not player:
            continue
        team = normalize_team_code(first_value(row, ["Team", "Tm"]))
        stolen_bases = to_int(first_value(row, ["SB"]))
        caught = to_int(first_value(row, ["CS"]))
        attempts = stolen_bases + caught
        runners.append(
            {
                "player": player,
                "playerId": first_value(row, ["Player-additional", "Name-additional", "player_id", "PlayerID", "ID"]),
                "team": team,
                "games": to_int(first_value(row, ["G", "Games"])),
                "stolenBases": stolen_bases,
                "caughtStealing": caught,
                "stolenBasePct": to_float(first_value(row, ["SB%", "SB Pct"]), stolen_bases / attempts if attempts else 0.0),
                "extraBasesTakenPct": to_float(first_value(row, ["XBT%", "XBT Pct"])),
                "runsFromBaserunning": to_float(first_value(row, ["Rbaser", "Baser", "BR"])),
            }
        )
    return runners


def parse_pitching(raw: str) -> list[dict[str, Any]]:
    pitchers: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        pitcher = clean_name(first_value(row, ["Player", "Name", "Pitcher"]))
        if not pitcher or is_summary_name(pitcher):
            continue
        team = normalize_team_code(first_value(row, ["Team", "Tm"]))
        innings = to_float(first_value(row, ["IP", "Innings"]))
        hits_allowed = to_int(first_value(row, ["H", "HA", "Hits", "Hits Allowed"]))
        batters_faced = to_int(first_value(row, ["BF", "BFP", "TBF", "PA"]))
        record = {
            "pitcher": pitcher,
            "pitcherId": first_value(row, ["Player-additional", "Name-additional", "-9999", "player_id", "PlayerID", "ID"]),
            "team": team,
            "league": first_value(row, ["Lg", "League"]),
            "games": to_int(first_value(row, ["G", "Games"])),
            "gamesStarted": to_int(first_value(row, ["GS"])),
            "innings": innings,
            "hitsAllowed": hits_allowed,
            "runsAllowed": to_int(first_value(row, ["R"])),
            "earnedRuns": to_int(first_value(row, ["ER"])),
            "homeRunsAllowed": to_int(first_value(row, ["HR"])),
            "walks": to_int(first_value(row, ["BB"])),
            "strikeouts": to_int(first_value(row, ["SO", "K"])),
            "battersFaced": batters_faced,
            "era": to_float(first_value(row, ["ERA"])),
            "fip": to_float(first_value(row, ["FIP"])),
            "whip": to_float(first_value(row, ["WHIP"])),
            "hitsPerNine": to_float(first_value(row, ["H9", "H/9"]), hits_allowed * 9 / innings if innings else 0.0),
        }
        if looks_like_standard_pitching_record(record):
            pitchers.append(record)
    return pitchers


def parse_batting_against(raw: str) -> list[dict[str, Any]]:
    against: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        pitcher = clean_name(first_value(row, ["Player", "Name", "Pitcher"]))
        if not pitcher or is_summary_name(pitcher):
            continue
        team = normalize_team_code(first_value(row, ["Team", "Tm"]))
        at_bats = to_int(first_value(row, ["AB"]))
        hits = to_int(first_value(row, ["H", "Hits"]))
        record = {
            "pitcher": pitcher,
            "pitcherId": first_value(row, ["Player-additional", "Name-additional", "-9999", "player_id", "PlayerID", "ID"]),
            "team": team,
            "innings": to_float(first_value(row, ["IP", "Innings"])),
            "plateAppearances": to_int(first_value(row, ["PA"])),
            "atBats": at_bats,
            "hitsAllowed": hits,
            "homeRunsAllowed": to_int(first_value(row, ["HR"])),
            "walks": to_int(first_value(row, ["BB"])),
            "strikeouts": to_int(first_value(row, ["SO", "K"])),
            "battingAverageAllowed": to_float(first_value(row, ["BA", "BAA", "AVG"]), hits / at_bats if at_bats else 0.0),
            "onBaseAllowed": to_float(first_value(row, ["OBP"])),
            "sluggingAllowed": to_float(first_value(row, ["SLG"])),
            "opsAllowed": to_float(first_value(row, ["OPS"])),
        }
        if any([record["atBats"], record["hitsAllowed"], record["battingAverageAllowed"], record["opsAllowed"]]):
            against.append(record)
    return against


def parse_team_batting_against(raw: str) -> list[dict[str, Any]]:
    teams: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        team = normalize_team_code(first_value(row, ["Team", "Tm", "Squad"]))
        if not team:
            continue
        at_bats = to_int(first_value(row, ["AB"]))
        hits = to_int(first_value(row, ["H", "Hits"]))
        record = {
            "team": team,
            "name": TEAM_NAMES.get(team, team),
            "games": to_int(first_value(row, ["G", "Games"])),
            "plateAppearances": to_int(first_value(row, ["PA"])),
            "atBats": at_bats,
            "hitsAllowed": hits,
            "homeRunsAllowed": to_int(first_value(row, ["HR"])),
            "walks": to_int(first_value(row, ["BB"])),
            "strikeouts": to_int(first_value(row, ["SO", "K"])),
            "battingAverageAllowed": to_float(first_value(row, ["BA", "BAA", "AVG"]), hits / at_bats if at_bats else 0.0),
            "onBaseAllowed": to_float(first_value(row, ["OBP"])),
            "sluggingAllowed": to_float(first_value(row, ["SLG"])),
            "opsAllowed": to_float(first_value(row, ["OPS"])),
        }
        if any([record["atBats"], record["hitsAllowed"], record["battingAverageAllowed"], record["opsAllowed"]]):
            teams.append(record)
    return teams


def parse_team_standard_pitching(raw: str) -> list[dict[str, Any]]:
    teams: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        team = normalize_team_code(first_value(row, ["Team", "Tm", "Squad"]))
        if not team:
            continue
        innings = to_float(first_value(row, ["IP", "Innings"]))
        hits_allowed = to_int(first_value(row, ["H", "HA", "Hits", "Hits Allowed"]))
        record = {
            "team": team,
            "name": TEAM_NAMES.get(team, team),
            "games": to_int(first_value(row, ["G", "Games"])),
            "gamesStarted": to_int(first_value(row, ["GS"])),
            "innings": innings,
            "hitsAllowed": hits_allowed,
            "runsAllowed": to_int(first_value(row, ["R"])),
            "earnedRuns": to_int(first_value(row, ["ER"])),
            "homeRunsAllowed": to_int(first_value(row, ["HR"])),
            "walks": to_int(first_value(row, ["BB"])),
            "strikeouts": to_int(first_value(row, ["SO", "K"])),
            "era": to_float(first_value(row, ["ERA"])),
            "fip": to_float(first_value(row, ["FIP"])),
            "whip": to_float(first_value(row, ["WHIP"])),
            "hitsPerNine": to_float(first_value(row, ["H9", "H/9"]), hits_allowed * 9 / innings if innings else 0.0),
        }
        if any([record["innings"], record["hitsAllowed"], record["era"], record["fip"], record["whip"], record["hitsPerNine"]]):
            teams.append(record)
    return teams


def parse_team_advanced_pitching(raw: str) -> list[dict[str, Any]]:
    teams: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        team = normalize_team_code(first_value(row, ["Team", "Tm", "Squad"]))
        if not team:
            continue
        record = {
            "team": team,
            "name": TEAM_NAMES.get(team, team),
            "innings": to_float(first_value(row, ["IP", "Innings"])),
            "strikeoutRate": to_rate(first_value(row, ["K%", "SO%", "SO/PA"])),
            "walkRate": to_rate(first_value(row, ["BB%", "BB/PA"])),
            "kMinusBbRate": to_rate(first_value(row, ["K-BB%", "SO-BB%"])),
            "homeRunRate": to_rate(first_value(row, ["HR%", "HR/PA"])),
            "eraMinus": to_float(first_value(row, ["ERA-", "ERA Minus"])),
            "fipMinus": to_float(first_value(row, ["FIP-", "FIP Minus"])),
            "xfipMinus": to_float(first_value(row, ["xFIP-", "xFIP Minus"])),
            "siera": to_float(first_value(row, ["SIERA"])),
            "xfip": to_float(first_value(row, ["xFIP"])),
            "fip": to_float(first_value(row, ["FIP"])),
        }
        if not record["kMinusBbRate"] and (record["strikeoutRate"] or record["walkRate"]):
            record["kMinusBbRate"] = record["strikeoutRate"] - record["walkRate"]
        if any(value for key, value in record.items() if key not in {"team", "name"}):
            teams.append(record)
    return teams


def parse_player_advanced_pitching(raw: str) -> list[dict[str, Any]]:
    pitchers: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        pitcher = clean_name(first_value(row, ["Player", "Name", "Pitcher"]))
        if not pitcher or is_summary_name(pitcher):
            continue
        record = {
            "pitcher": pitcher,
            "pitcherId": first_value(row, ["Player-additional", "Name-additional", "-9999", "player_id", "PlayerID", "ID"]),
            "team": normalize_team_code(first_value(row, ["Team", "Tm"])),
            "innings": to_float(first_value(row, ["IP", "Innings"])),
            "strikeoutRate": to_rate(first_value(row, ["K%", "SO%", "SO/PA"])),
            "walkRate": to_rate(first_value(row, ["BB%", "BB/PA"])),
            "kMinusBbRate": to_rate(first_value(row, ["K-BB%", "SO-BB%"])),
            "homeRunRate": to_rate(first_value(row, ["HR%", "HR/PA"])),
            "eraMinus": to_float(first_value(row, ["ERA-", "ERA Minus"])),
            "fipMinus": to_float(first_value(row, ["FIP-", "FIP Minus"])),
            "xfipMinus": to_float(first_value(row, ["xFIP-", "xFIP Minus"])),
            "siera": to_float(first_value(row, ["SIERA"])),
            "xfip": to_float(first_value(row, ["xFIP"])),
            "fip": to_float(first_value(row, ["FIP"])),
        }
        if not record["kMinusBbRate"] and (record["strikeoutRate"] or record["walkRate"]):
            record["kMinusBbRate"] = record["strikeoutRate"] - record["walkRate"]
        if any(value for key, value in record.items() if key not in {"pitcher", "pitcherId", "team"}):
            pitchers.append(record)
    return pitchers


def parse_batter_pitcher_advanced(raw: str) -> list[dict[str, Any]]:
    matchups: list[dict[str, Any]] = []
    for row in normalize_rows(raw):
        batter = clean_name(first_value(row, ["Batter", "Player", "Name", "Hitter"]))
        pitcher = clean_name(first_value(row, ["Pitcher", "Opposing Pitcher", "P"]))
        if not batter or not pitcher:
            continue
        plate_appearances = to_int(first_value(row, ["PA", "Plate Appearances"]))
        at_bats = to_int(first_value(row, ["AB", "At Bats"]))
        hits = to_int(first_value(row, ["H", "Hits"]))
        home_runs = to_int(first_value(row, ["HR", "Home Runs"]))
        strikeouts = to_int(first_value(row, ["SO", "K", "Strikeouts"]))
        walks = to_int(first_value(row, ["BB", "Walks"]))
        record = {
            "batter": batter,
            "batterId": first_value(row, ["Batter-additional", "Player-additional", "Name-additional", "batter_id", "BatterID"]),
            "pitcher": pitcher,
            "pitcherId": first_value(row, ["Pitcher-additional", "pitcher_id", "PitcherID", "P-ID"]),
            "pitcherTeam": normalize_team_code(first_value(row, ["PitcherTeam", "Pitcher Tm", "Tm", "Team"])),
            "plateAppearances": plate_appearances,
            "atBats": at_bats,
            "hits": hits,
            "homeRuns": home_runs,
            "walks": walks,
            "strikeouts": strikeouts,
            "battingAverage": to_float(first_value(row, ["BA", "AVG"]), hits / at_bats if at_bats else 0.0),
            "onBase": to_float(first_value(row, ["OBP"])),
            "slugging": to_float(first_value(row, ["SLG"])),
            "ops": to_float(first_value(row, ["OPS"])),
            "woba": to_float(first_value(row, ["wOBA", "WOBA"])),
            "xwoba": to_float(first_value(row, ["xwOBA", "XWOBA"])),
            "xba": to_float(first_value(row, ["xBA", "XBA"])),
            "xslg": to_float(first_value(row, ["xSLG", "XSLG"])),
            "exitVelocity": to_float(first_value(row, ["EV", "Exit Velocity", "Avg EV"])),
            "launchAngle": to_float(first_value(row, ["LA", "Launch Angle", "Avg LA"])),
            "hardHitRate": to_rate(first_value(row, ["HardH%", "HardHit%", "Hard Hit%", "Hard-Hit%"])),
            "barrelRate": to_rate(first_value(row, ["Barrel%", "Barrels/PA%"])),
            "whiffRate": to_rate(first_value(row, ["Whiff%", "Whiff Rate"])),
            "chaseRate": to_rate(first_value(row, ["Chase%", "O-Swing%"])),
        }
        if any([plate_appearances, at_bats, hits, home_runs, strikeouts, record["woba"], record["xwoba"], record["barrelRate"]]):
            matchups.append(record)
    return matchups


def load_players() -> list[Player]:
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return [Player(**item) for item in data]
    if DEFAULT_CSV.exists():
        raw = DEFAULT_CSV.read_text(encoding="utf-8-sig", errors="replace")
        players = parse_players(raw)
        save_players(players)
        return players
    return []


def save_players(players: list[Player]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps([asdict(player) for player in players], indent=2), encoding="utf-8")


def player_record_key(player: Player) -> str:
    if player.player_id:
        return player.player_id.strip().lower()
    return f"{player.player.strip().lower()}|{normalize_team_code(player.team)}"


def merge_players(new_players: list[Player]) -> list[Player]:
    existing_players = load_players()
    merged: dict[str, Player] = {
        player_record_key(player): player for player in existing_players if player_record_key(player).strip("|")
    }
    for player in new_players:
        key = player_record_key(player)
        if not key.strip("|"):
            continue
        name_team_key = f"{player.player.strip().lower()}|{normalize_team_code(player.team)}"
        for existing_key, existing_player in list(merged.items()):
            existing_name_team_key = f"{existing_player.player.strip().lower()}|{normalize_team_code(existing_player.team)}"
            if existing_name_team_key == name_team_key and existing_key != key:
                player = Player(**{**asdict(existing_player), **asdict(player)})
                if not player.player_id:
                    player.player_id = existing_player.player_id
                del merged[existing_key]
                key = player_record_key(player)
                break
        merged[key] = player
    players = sorted(merged.values(), key=lambda item: (normalize_team_code(item.team), item.player))
    save_players(players)
    return players


def player_from_mlb_payload(payload: dict[str, Any], existing: Player | None = None) -> Player:
    player_info = payload.get("player", {})
    batting = payload.get("batting", {})
    player_id = str(player_info.get("id") or "").strip()
    doubles = to_int(batting.get("doubles"))
    triples = to_int(batting.get("triples"))
    home_runs = to_int(batting.get("homeRuns"))
    hits = to_int(batting.get("hits"))
    listed_total_bases = to_int(batting.get("totalBases"))
    singles = max(hits - doubles - triples - home_runs, 0)
    total_bases = listed_total_bases or singles + doubles * 2 + triples * 3 + home_runs * 4
    team = normalize_team_code(str(player_info.get("currentTeam") or ""))
    if not team and existing:
        team = existing.team
    resolved_player_id = existing.player_id if existing and existing.player_id else f"mlb-{player_id}"
    return Player(
        player=str(player_info.get("name") or (existing.player if existing else "")).strip(),
        team=team,
        league=existing.league if existing else "",
        games=to_int(batting.get("games")),
        plate_appearances=to_int(batting.get("plateAppearances")),
        at_bats=to_int(batting.get("atBats")),
        hits=hits,
        doubles=doubles,
        triples=triples,
        home_runs=home_runs,
        walks=to_int(batting.get("walks")),
        strikeouts=to_int(batting.get("strikeouts")),
        batting_average=to_float(batting.get("battingAverage")),
        on_base=to_float(batting.get("onBase")),
        slugging=to_float(batting.get("slugging")),
        ops=to_float(batting.get("ops")),
        total_bases=total_bases,
        player_id=resolved_player_id,
    )


def batting_payload_has_signal(payload: dict[str, Any]) -> bool:
    batting = payload.get("batting", {})
    return any(to_int(batting.get(key)) > 0 for key in ["games", "plateAppearances", "atBats", "hits", "homeRuns"])


def pitching_payload_has_signal(payload: dict[str, Any]) -> bool:
    pitching = payload.get("pitching", {})
    return any(
        [
            to_float(pitching.get("innings")) > 0,
            to_int(pitching.get("gamesStarted")) > 0,
            to_int(pitching.get("strikeouts")) > 0,
            to_float(pitching.get("era")) > 0,
            to_float(pitching.get("whip")) > 0,
        ]
    )


def pitcher_from_mlb_payload(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    player_info = payload.get("player", {})
    pitching = payload.get("pitching", {})
    player_id = str(player_info.get("id") or "").strip()
    innings = to_float(pitching.get("innings"))
    strikeouts = to_int(pitching.get("strikeouts"))
    walks = to_int(pitching.get("walks"))
    batters_faced = to_int(pitching.get("battersFaced"))
    if not batters_faced and innings:
        batters_faced = int(round(innings * 4.25))
    team = normalize_team_code(str(player_info.get("currentTeam") or ""))
    if not team and existing:
        team = normalize_team_code(str(existing.get("team", "")))
    return {
        "pitcher": str(player_info.get("name") or (existing or {}).get("pitcher") or "").strip(),
        "pitcherId": (existing or {}).get("pitcherId") or f"mlb-{player_id}" if player_id else (existing or {}).get("pitcherId", ""),
        "team": team,
        "league": (existing or {}).get("league", ""),
        "throws": player_info.get("pitchHand") or (existing or {}).get("throws", ""),
        "games": to_int(pitching.get("games")),
        "gamesStarted": to_int(pitching.get("gamesStarted")),
        "innings": innings,
        "hitsAllowed": to_int(pitching.get("hitsAllowed")),
        "runsAllowed": to_int(pitching.get("runsAllowed")),
        "earnedRuns": to_int(pitching.get("earnedRuns")),
        "homeRunsAllowed": to_int(pitching.get("homeRunsAllowed")),
        "walks": walks,
        "strikeouts": strikeouts,
        "battersFaced": batters_faced,
        "era": to_float(pitching.get("era")),
        "fip": to_float(pitching.get("fip")),
        "whip": to_float(pitching.get("whip")),
        "hitsPerNine": to_float(pitching.get("hitsPerNine")),
    }


def upsert_pitcher_from_mlb_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not pitching_payload_has_signal(payload):
        return {"action": "skipped", "reason": "No pitching stat line found."}
    pitchers = load_pitching()
    player_info = payload.get("player", {})
    mlb_player_id = str(player_info.get("id") or "").strip()
    mlb_key = f"mlb-{mlb_player_id}" if mlb_player_id else ""
    name = str(player_info.get("name") or "").strip().lower()
    existing_index = next(
        (
            index
            for index, pitcher in enumerate(pitchers)
            if (mlb_key and pitcher.get("pitcherId") == mlb_key) or (name and pitcher.get("pitcher", "").lower() == name)
        ),
        None,
    )
    existing = pitchers[existing_index] if existing_index is not None else None
    pitcher = pitcher_from_mlb_payload(payload, existing)
    if not looks_like_standard_pitching_record(pitcher):
        return {"action": "skipped", "reason": "Lookup did not include usable pitching volume."}
    if existing_index is None:
        pitchers.append(pitcher)
        action = "added"
    else:
        pitchers[existing_index] = {**existing, **pitcher}
        action = "updated"
    save_json_file(PITCHING_FILE, sorted(pitchers, key=lambda item: (normalize_team_code(item.get("team", "")), item.get("pitcher", ""))))
    update_dataset_meta("pitching", f"MLB StatsAPI {payload.get('season', '')}".strip(), len(pitchers))
    return {
        "action": action,
        "pitcherKey": record_key(pitcher, ["pitcherId"]) or record_key(pitcher, ["pitcher", "team"]),
        "pitcher": pitcher,
        "count": len(pitchers),
    }


def upsert_player_from_mlb_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not batting_payload_has_signal(payload):
        return {"action": "skipped", "reason": "No batting stat line found."}
    players = load_players()
    player_info = payload.get("player", {})
    mlb_player_id = str(player_info.get("id") or "").strip()
    mlb_key = f"mlb-{mlb_player_id}" if mlb_player_id else ""
    name = str(player_info.get("name") or "").strip().lower()
    existing_index = next(
        (
            index
            for index, player in enumerate(players)
            if (mlb_key and player.player_id == mlb_key) or (name and player.player.lower() == name)
        ),
        None,
    )
    existing = players[existing_index] if existing_index is not None else None
    player = player_from_mlb_payload(payload, existing)
    if existing_index is None:
        players.append(player)
        action = "added"
    else:
        players[existing_index] = player
        action = "updated"
    save_players(players)
    update_dataset_meta("batting", f"MLB StatsAPI {payload.get('season', '')}".strip(), len(players))
    return {
        "action": action,
        "playerId": player.player_id,
        "player": asdict(player),
        "count": len(players),
    }


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_file(path: Path, payload: Any) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_opponents() -> list[dict[str, Any]]:
    return load_json_file(OPPONENT_FILE, [])


def load_game_logs() -> list[dict[str, Any]]:
    return load_json_file(GAME_LOG_FILE, [])


def load_pitching_game_logs() -> list[dict[str, Any]]:
    return load_json_file(PITCHING_GAME_LOG_FILE, [])


def load_team_game_logs() -> list[dict[str, Any]]:
    return load_json_file(TEAM_GAME_LOG_FILE, [])


def load_team_batting() -> list[dict[str, Any]]:
    return load_json_file(TEAM_BATTING_FILE, [])


def load_baserunning() -> list[dict[str, Any]]:
    return load_json_file(BASERUNNING_FILE, [])


def load_pitching() -> list[dict[str, Any]]:
    return load_json_file(PITCHING_FILE, [])


def load_batting_against() -> list[dict[str, Any]]:
    return load_json_file(BATTING_AGAINST_FILE, [])


def load_team_batting_against() -> list[dict[str, Any]]:
    return load_json_file(TEAM_BATTING_AGAINST_FILE, [])


def load_team_advanced_pitching() -> list[dict[str, Any]]:
    return load_json_file(TEAM_ADVANCED_PITCHING_FILE, [])


def load_player_advanced_pitching() -> list[dict[str, Any]]:
    return load_json_file(PLAYER_ADVANCED_PITCHING_FILE, [])


def load_team_standard_pitching() -> list[dict[str, Any]]:
    return load_json_file(TEAM_STANDARD_PITCHING_FILE, [])


def load_batter_pitcher_advanced() -> list[dict[str, Any]]:
    return load_json_file(BATTER_PITCHER_ADVANCED_FILE, [])


def load_statcast_quality() -> list[dict[str, Any]]:
    return load_json_file(STATCAST_QUALITY_FILE, [])


def load_handedness_splits() -> list[dict[str, Any]]:
    return load_json_file(HANDEDNESS_SPLITS_FILE, [])


def load_rolling_form() -> list[dict[str, Any]]:
    return load_json_file(ROLLING_FORM_FILE, [])


def load_pitch_arsenal() -> list[dict[str, Any]]:
    return load_json_file(PITCH_ARSENAL_FILE, [])


def load_game_context() -> list[dict[str, Any]]:
    return load_json_file(GAME_CONTEXT_FILE, [])


def load_ballpark_context() -> list[dict[str, Any]]:
    return load_json_file(BALLPARK_CONTEXT_FILE, [])


def load_pitcher_options() -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    name_keys: dict[str, str] = {}

    def add_pitcher(pitcher: dict[str, Any]) -> None:
        if not looks_like_pitcher_option(pitcher):
            return
        id_key = record_key(pitcher, ["pitcherId"])
        name_key = record_key(pitcher, ["pitcher", "team"])
        key = id_key or name_key
        if name_key and name_key in name_keys:
            key = name_keys[name_key]
        elif id_key:
            existing_key = next(
                (
                    stored_key
                    for stored_key, stored_pitcher in combined.items()
                    if record_key(stored_pitcher, ["pitcher", "team"]) == name_key
                ),
                "",
            )
            if existing_key:
                key = existing_key
        if not key.strip("|"):
            return
        combined[key] = {**combined.get(key, {}), **pitcher}
        if name_key:
            name_keys[name_key] = key

    for pitcher in load_pitching():
        add_pitcher(pitcher)
    for pitcher in load_batting_against():
        add_pitcher(pitcher)
    for pitcher in load_player_advanced_pitching():
        add_pitcher(pitcher)
    options = []
    for key, pitcher in combined.items():
        if not looks_like_pitcher_option(pitcher):
            continue
        pitcher["key"] = key
        options.append(pitcher)
    return sorted(options, key=lambda item: (item.get("team", ""), item.get("pitcher", "")))


def load_dataset_meta() -> dict[str, Any]:
    defaults = {
        "batting": {"loaded": DATA_FILE.exists(), "count": len(load_players()) if DATA_FILE.exists() else 0},
        "opponents": {"loaded": OPPONENT_FILE.exists(), "count": len(load_opponents())},
        "gameLogs": {"loaded": GAME_LOG_FILE.exists(), "count": len(load_game_logs())},
        "pitchingGameLogs": {"loaded": PITCHING_GAME_LOG_FILE.exists(), "count": len(load_pitching_game_logs())},
        "teamGameLogs": {"loaded": TEAM_GAME_LOG_FILE.exists(), "count": len(load_team_game_logs())},
        "teamBatting": {"loaded": TEAM_BATTING_FILE.exists(), "count": len(load_team_batting())},
        "baserunning": {"loaded": BASERUNNING_FILE.exists(), "count": len(load_baserunning())},
        "pitching": {"loaded": PITCHING_FILE.exists(), "count": len(load_pitching())},
        "battingAgainst": {"loaded": BATTING_AGAINST_FILE.exists(), "count": len(load_batting_against())},
        "teamBattingAgainst": {"loaded": TEAM_BATTING_AGAINST_FILE.exists(), "count": len(load_team_batting_against())},
        "teamAdvancedPitching": {"loaded": TEAM_ADVANCED_PITCHING_FILE.exists(), "count": len(load_team_advanced_pitching())},
        "playerAdvancedPitching": {"loaded": PLAYER_ADVANCED_PITCHING_FILE.exists(), "count": len(load_player_advanced_pitching())},
        "teamStandardPitching": {"loaded": TEAM_STANDARD_PITCHING_FILE.exists(), "count": len(load_team_standard_pitching())},
        "batterPitcherAdvanced": {"loaded": BATTER_PITCHER_ADVANCED_FILE.exists(), "count": len(load_batter_pitcher_advanced())},
        "statcastQuality": {"loaded": STATCAST_QUALITY_FILE.exists(), "count": len(load_statcast_quality())},
        "handednessSplits": {"loaded": HANDEDNESS_SPLITS_FILE.exists(), "count": len(load_handedness_splits())},
        "rollingForm": {"loaded": ROLLING_FORM_FILE.exists(), "count": len(load_rolling_form())},
        "pitchArsenal": {"loaded": PITCH_ARSENAL_FILE.exists(), "count": len(load_pitch_arsenal())},
        "gameContext": {"loaded": GAME_CONTEXT_FILE.exists(), "count": len(load_game_context())},
        "ballparkContext": {"loaded": BALLPARK_CONTEXT_FILE.exists(), "count": len(load_ballpark_context())},
    }
    stored = load_json_file(DATASET_META_FILE, {})
    return {key: {**defaults[key], **stored.get(key, {})} for key in defaults}


def update_dataset_meta(kind: str, filename: str, count: int) -> dict[str, Any]:
    meta = load_dataset_meta()
    files = list(dict.fromkeys([*meta.get(kind, {}).get("files", []), filename]))
    meta[kind] = {"loaded": True, "filename": filename, "files": files, "count": count}
    save_json_file(DATASET_META_FILE, meta)
    return meta


def dataset_source_id(kind: str, url: str) -> str:
    digest = hashlib.sha1(f"{kind}|{url}".encode("utf-8")).hexdigest()
    return digest[:16]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_dataset_sources() -> list[dict[str, Any]]:
    sources = load_json_file(DATASET_SOURCE_FILE, [])
    return sorted(sources, key=lambda item: (item.get("type", ""), item.get("url", "")))


def save_dataset_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    save_json_file(DATASET_SOURCE_FILE, sources)
    return load_dataset_sources()


def upsert_dataset_source(
    url: str,
    kind: str,
    filename: str,
    count: int,
    status: str = "loaded",
    error: str = "",
) -> list[dict[str, Any]]:
    sources = load_dataset_sources()
    source_id = dataset_source_id(kind, url)
    existing = next((item for item in sources if item.get("id") == source_id), {})
    updated = {
        **existing,
        "id": source_id,
        "type": kind,
        "url": url,
        "filename": filename,
        "lastCount": count,
        "lastStatus": status,
        "lastError": error,
        "lastImportedAt": utc_now_iso(),
        "autoRefresh": existing.get("autoRefresh", True),
        "refreshCadence": existing.get("refreshCadence", "daily"),
    }
    sources = [item for item in sources if item.get("id") != source_id]
    sources.append(updated)
    return save_dataset_sources(sources)


def mark_dataset_source_error(source: dict[str, Any], error: str) -> list[dict[str, Any]]:
    sources = load_dataset_sources()
    updated = {
        **source,
        "lastStatus": "error",
        "lastError": error,
        "lastImportedAt": utc_now_iso(),
    }
    sources = [item for item in sources if item.get("id") != source.get("id")]
    sources.append(updated)
    return save_dataset_sources(sources)


def attach_dataset_source(
    payload: dict[str, Any],
    dataset_url: str,
    kind: str,
    filename: str,
    count: int,
) -> dict[str, Any]:
    if dataset_url:
        sources = upsert_dataset_source(dataset_url, kind, filename, count)
        payload["sources"] = sources
        payload["datasetSources"] = sources
    return payload


def process_dataset_payload(csv_type: str, raw: str, filename: str, dataset_url: str = "") -> dict[str, Any]:
    configs = {
        "opponents": {
            "parser": parse_opponents,
            "path": OPPONENT_FILE,
            "keys": ["team"],
            "payload_key": "opponents",
            "error": "No opponent rows found. Try a team/pitching CSV with Team/Tm plus BA allowed, H, IP, ERA, or WHIP.",
        },
        "gameLogs": {
            "parser": parse_game_logs,
            "path": GAME_LOG_FILE,
            "keys": ["sourceId", "playerId", "player", "opponent"],
            "payload_key": "gameLogs",
            "error": "No game-log rows found. Try a CSV with Player, Opponent/Opp, AB, and H columns.",
        },
        "pitchingGameLogs": {
            "parser": parse_pitching_game_logs,
            "path": PITCHING_GAME_LOG_FILE,
            "keys": ["sourceId", "pitcherId", "pitcher", "opponent"],
            "payload_key": "pitchingGameLogs",
            "error": "No pitching game-log rows found. Try a CSV with Pitcher, Opponent/Opp, IP, H, BB, SO, ER, or BF columns.",
        },
        "teamGameLogs": {
            "parser": lambda text: parse_team_game_logs(text, team_from_dataset_url(dataset_url)),
            "path": TEAM_GAME_LOG_FILE,
            "keys": ["sourceId", "team", "date", "opponent", "opposingPitcher"],
            "payload_key": "teamGameLogs",
            "error": "No team game-log rows found. Try a team batting game log with Date, Opp, Rslt, RS, RA, AB, H, HR, BB, SO, OPS, and Opp Starter columns.",
        },
        "teamBatting": {
            "parser": parse_team_batting,
            "path": TEAM_BATTING_FILE,
            "keys": ["team"],
            "payload_key": "teamBatting",
            "error": "No team batting rows found. Try a CSV with Team/Tm plus G, AB, H, BA, OPS, or R/G columns.",
        },
        "baserunning": {
            "parser": parse_baserunning,
            "path": BASERUNNING_FILE,
            "keys": ["playerId", "player", "team"],
            "payload_key": "baserunning",
            "error": "No baserunning rows found. Try a CSV with Player plus SB, CS, or XBT% columns.",
        },
        "pitching": {
            "parser": parse_pitching,
            "path": PITCHING_FILE,
            "keys": ["pitcherId", "pitcher", "team"],
            "payload_key": "pitching",
            "error": "No pitching rows found. Try a CSV with Player, Team/Tm, IP, H, ERA, WHIP, or H9 columns.",
        },
        "battingAgainst": {
            "parser": parse_batting_against,
            "path": BATTING_AGAINST_FILE,
            "keys": ["pitcherId", "pitcher", "team"],
            "payload_key": "battingAgainst",
            "error": "No batting-against rows found. Try a CSV with Player, Team/Tm, AB, H, BA, OBP, SLG, or OPS columns.",
        },
        "teamBattingAgainst": {
            "parser": parse_team_batting_against,
            "path": TEAM_BATTING_AGAINST_FILE,
            "keys": ["team"],
            "payload_key": "teamBattingAgainst",
            "error": "No team batting-against rows found. Try a CSV with Team/Tm plus AB, H, BA, OBP, SLG, or OPS columns.",
        },
        "teamAdvancedPitching": {
            "parser": parse_team_advanced_pitching,
            "path": TEAM_ADVANCED_PITCHING_FILE,
            "keys": ["team"],
            "payload_key": "teamAdvancedPitching",
            "error": "No team advanced pitching rows found. Try a CSV with Team/Tm plus ERA-, FIP-, K%, BB%, K-BB%, SIERA, xFIP, or FIP columns.",
        },
        "playerAdvancedPitching": {
            "parser": parse_player_advanced_pitching,
            "path": PLAYER_ADVANCED_PITCHING_FILE,
            "keys": ["pitcherId", "pitcher", "team"],
            "payload_key": "playerAdvancedPitching",
            "error": "No player advanced pitching rows found. Try a CSV with Player, Team/Tm plus ERA-, FIP-, K%, BB%, K-BB%, SIERA, xFIP, or FIP columns.",
        },
        "teamStandardPitching": {
            "parser": parse_team_standard_pitching,
            "path": TEAM_STANDARD_PITCHING_FILE,
            "keys": ["team"],
            "payload_key": "teamStandardPitching",
            "error": "No team standard pitching rows found. Try a CSV with Team/Tm plus IP, H, ERA, WHIP, H9, SO, or BB columns.",
        },
        "batterPitcherAdvanced": {
            "parser": parse_batter_pitcher_advanced,
            "path": BATTER_PITCHER_ADVANCED_FILE,
            "keys": ["batterId", "batter", "pitcherId", "pitcher"],
            "payload_key": "batterPitcherAdvanced",
            "error": "No batter-vs-pitcher rows found. Try a CSV with Batter, Pitcher, PA, AB, H, HR, SO, BA/OPS, wOBA/xwOBA, Barrel%, or Whiff% columns.",
        },
        "ballparkContext": {
            "parser": parse_ballpark_context,
            "path": BALLPARK_CONTEXT_FILE,
            "keys": ["gameId", "date", "homeTeam", "awayTeam", "venue"],
            "payload_key": "ballparkContext",
            "error": "No ballpark context rows found. Try a CSV with Home Team, Away Team, Venue, Temperature, Wind MPH, Wind Direction, Roof, Park Factor, and HR Factor columns.",
        },
    }

    if csv_type == "batting":
        players = parse_players(raw)
        if not players:
            raise ValueError("No player rows found. Check that the CSV includes Player, G, AB, H, and BA columns.")
        merged_players = merge_players(players)
        meta = update_dataset_meta("batting", filename, len(merged_players))
        payload = {
            "type": csv_type,
            "count": len(merged_players),
            "players": [asdict(player) for player in merged_players],
            "datasets": meta,
        }
        return attach_dataset_source(payload, dataset_url, csv_type, filename, len(merged_players))

    config = configs.get(csv_type)
    if not config:
        raise ValueError("Unsupported CSV type")

    records = config["parser"](raw)
    if not records:
        raise ValueError(str(config["error"]))
    if csv_type in {"gameLogs", "pitchingGameLogs", "teamGameLogs"}:
        source_key = dataset_source_id(csv_type, dataset_url or filename)
        for record in records:
            record["sourceId"] = source_key
    merged = merge_records(config["path"], records, config["keys"])
    meta = update_dataset_meta(csv_type, filename, len(merged))
    payload = {
        "type": csv_type,
        "count": len(merged),
        str(config["payload_key"]): merged,
        "pitchers": load_pitcher_options(),
        "datasets": meta,
    }
    return attach_dataset_source(payload, dataset_url, csv_type, filename, len(merged))


def refresh_dataset_sources(source_id: str = "all") -> dict[str, Any]:
    with DATASET_REFRESH_LOCK:
        sources = load_dataset_sources()
        if source_id in {"", "all"}:
            selected = sources
        else:
            selected = [source for source in sources if source.get("id") == source_id]

        if not selected:
            raise ValueError("No stored dataset URL found.")

        results = []
        for source in selected:
            url = str(source.get("url", "")).strip()
            csv_type = str(source.get("type", "")).strip()
            if not url or not csv_type:
                error = "Stored source is missing a URL or dataset type."
                mark_dataset_source_error(source, error)
                results.append({"id": source.get("id", ""), "type": csv_type, "status": "error", "error": error})
                continue
            try:
                raw, filename = fetch_dataset_url(url)
                payload = process_dataset_payload(csv_type, raw, filename, url)
                results.append(
                    {
                        "id": source.get("id", ""),
                        "type": csv_type,
                        "status": "loaded",
                        "count": payload.get("count", 0),
                        "filename": filename,
                    }
                )
            except ValueError as error:
                mark_dataset_source_error(source, str(error))
                results.append({"id": source.get("id", ""), "type": csv_type, "status": "error", "error": str(error)})

        return {
            "sources": load_dataset_sources(),
            "datasets": load_dataset_meta(),
            "pitchers": load_pitcher_options(),
            "results": results,
        }


def parse_source_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def dataset_source_due(source: dict[str, Any], now: datetime | None = None) -> bool:
    if source.get("autoRefresh") is False:
        return False
    timestamp = parse_source_time(source.get("lastImportedAt"))
    if timestamp is None:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        refresh_seconds = int(os.environ.get("DATASET_AUTO_REFRESH_SECONDS", str(DATASET_AUTO_REFRESH_SECONDS)))
    except ValueError:
        refresh_seconds = DATASET_AUTO_REFRESH_SECONDS
    return now - timestamp >= timedelta(seconds=refresh_seconds)


def refresh_due_dataset_sources(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    due_sources = [source for source in load_dataset_sources() if dataset_source_due(source, now)]
    results: list[dict[str, Any]] = []
    for source in due_sources:
        source_id = str(source.get("id", ""))
        if not source_id:
            continue
        try:
            payload = refresh_dataset_sources(source_id)
            results.extend(payload.get("results", []))
        except ValueError as error:
            mark_dataset_source_error(source, str(error))
            results.append({"id": source_id, "type": source.get("type", ""), "status": "error", "error": str(error)})
    return {
        "sources": load_dataset_sources(),
        "datasets": load_dataset_meta(),
        "pitchers": load_pitcher_options(),
        "results": results,
    }


def dataset_auto_refresh_worker() -> None:
    while True:
        try:
            payload = refresh_due_dataset_sources()
            if payload.get("results"):
                print(f"Daily dataset refresh checked {len(payload['results'])} source(s).")
        except Exception as error:  # pragma: no cover - keeps the background worker alive.
            print(f"Daily dataset refresh failed: {error}")
        time.sleep(60 * 60)


def start_dataset_auto_refresh() -> None:
    if os.environ.get("DATASET_AUTO_REFRESH", "1").strip().lower() in {"0", "false", "no"}:
        return
    thread = threading.Thread(target=dataset_auto_refresh_worker, name="dataset-auto-refresh", daemon=True)
    thread.start()


def model_data_needs() -> dict[str, Any]:
    meta = load_dataset_meta()
    checks = [
        ("batting", "Player batting baseline", "Loaded", "Required for every prop."),
        ("teamBattingAgainst", "Team batting-against", "Useful", "Improves opponent difficulty for hits and home runs."),
        ("teamStandardPitching", "Team standard pitching", "Useful", "Improves hits, home runs, and strikeout environment."),
        ("teamAdvancedPitching", "Team advanced pitching", "Useful", "Adds strikeout, walk, and quality indicators."),
        ("teamGameLogs", "Team game logs", "Useful", "Adds team-vs-team win rate, recent matchup form, runs, OPS, HR, walk, and strikeout context."),
        ("battingAgainst", "Player batting against", "Useful", "Improves selected pitcher context."),
        ("playerAdvancedPitching", "Player advanced pitching", "Useful", "Improves selected pitcher strikeout and quality context."),
        ("gameLogs", "Batter game logs by opponent", "Missing", "Adds recent form and player-vs-team history."),
        ("pitchingGameLogs", "Pitching game logs by opponent", "Missing", "Adds pitcher recent workload, strikeouts, and opponent-specific pitching history."),
        ("pitching", "Player standard pitching", "Missing", "Adds innings, batters faced, strikeouts, HR allowed, WHIP, and H/9 by pitcher."),
        ("batterPitcherAdvanced", "Advanced batter-vs-pitcher matchups", "Missing", "Adds exact batter/pitcher PA, H, HR, SO, wOBA/xwOBA, barrels, and whiffs."),
        ("statcastQuality", "Statcast quality metrics", "Missing", "Adds xBA, xSLG, xwOBA, barrel%, hard-hit%, launch angle, and exit velocity."),
        ("handednessSplits", "Handedness splits", "Missing", "Adds batter vs LHP/RHP and pitcher vs LHB/RHB context."),
        ("rollingForm", "Rolling Statcast form", "Missing", "Adds last 7/14/30 day PA, H, HR, SO, barrel, hard-hit, and K% form."),
        ("pitchArsenal", "Pitch arsenal", "Missing", "Adds pitch type usage, whiff, velocity, and barrel contact by pitcher."),
        ("gameContext", "Starter, lineup, park, and weather context", "Missing", "Adds probable starters, venue, roof/weather/wind, and lineup context when available."),
        ("ballparkContext", "Ballpark weather and park factors", "Missing", "Adds BallparkPal or imported venue weather, roof, wind, hit factor, and HR environment."),
    ]
    loaded = []
    missing = []
    for key, label, default_status, reason in checks:
        item = {
            "key": key,
            "label": label,
            "loaded": bool(meta.get(key, {}).get("loaded")),
            "count": meta.get(key, {}).get("count", 0),
            "reason": reason,
        }
        if item["loaded"]:
            loaded.append(item)
        elif default_status == "Missing":
            missing.append(item)

    useful = [
        "Confirmed starter data when ESPN has not posted a probable pitcher or the pitcher cannot be matched to uploaded rows.",
        "Batter and pitcher handedness splits: vs LHP/RHP for AVG, OPS, HR%, K%, BB%, wOBA, xwOBA.",
        "Recent rolling form: last 7/14/30 days for PA, H, HR, SO, barrel rate, hard-hit rate, and K%.",
        "Confirmed lineups, lineup spot, and batting order, because plate appearances drive every prop.",
        "Park factor, weather, roof status, and wind for home run and hit environment.",
        "BallparkPal API/export data for venue-specific weather-adjusted hit and home run factors.",
        "Pitch arsenal and batter performance vs pitch type, especially whiff rate and barrel rate.",
        "Statcast quality metrics: xBA, xSLG, xwOBA, barrel%, hard-hit%, launch angle, exit velocity.",
        "Use the Model Data Refresh action for a selected batter/pitcher/team to pull source data into saved JSON files.",
        "Sportsbook lines/results history if you want to train and back-test prop accuracy.",
    ]
    return {"loaded": loaded, "missing": missing, "useful": useful}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def opponent_adjustment(opponent_code: str, opponents: list[dict[str, Any]]) -> tuple[float, dict[str, Any] | None]:
    opponent = next((item for item in opponents if item.get("team") == opponent_code), None)
    if not opponent:
        return 0.0, None
    adjustment = 0.0
    if opponent.get("battingAverageAllowed"):
        adjustment += (opponent["battingAverageAllowed"] - 0.245) * 120
    if opponent.get("hitsPerNine"):
        adjustment += (opponent["hitsPerNine"] - 8.2) * 1.25
    if opponent.get("whip"):
        adjustment += (opponent["whip"] - 1.28) * 7
    if opponent.get("era"):
        adjustment += (opponent["era"] - 4.15) * 0.8
    return clamp(adjustment, -14, 14), opponent


def team_pitching_adjustment(opponent_code: str) -> tuple[float, dict[str, Any]]:
    details: dict[str, Any] = {}
    adjustment = 0.0

    batting_against = next((item for item in load_team_batting_against() if item.get("team") == opponent_code), None)
    if batting_against:
        details["battingAgainst"] = batting_against
        if batting_against.get("battingAverageAllowed"):
            adjustment += (batting_against["battingAverageAllowed"] - 0.245) * 125
        if batting_against.get("opsAllowed"):
            adjustment += (batting_against["opsAllowed"] - 0.720) * 18

    standard = next((item for item in load_team_standard_pitching() if item.get("team") == opponent_code), None)
    if standard:
        details["standardPitching"] = standard
        if standard.get("hitsPerNine"):
            adjustment += (standard["hitsPerNine"] - 8.2) * 1.25
        if standard.get("whip"):
            adjustment += (standard["whip"] - 1.28) * 7
        if standard.get("era"):
            adjustment += (standard["era"] - 4.15) * 0.7

    advanced = next((item for item in load_team_advanced_pitching() if item.get("team") == opponent_code), None)
    if advanced:
        details["advancedPitching"] = advanced
        if advanced.get("eraMinus"):
            adjustment += (advanced["eraMinus"] - 100) * 0.08
        if advanced.get("fipMinus"):
            adjustment += (advanced["fipMinus"] - 100) * 0.08
        if advanced.get("kMinusBbRate"):
            adjustment -= (advanced["kMinusBbRate"] - 0.145) * 18
        if advanced.get("siera"):
            adjustment += (advanced["siera"] - 4.15) * 0.7

    return clamp(adjustment, -16, 16), details


def game_log_matchup(player: Player, opponent_code: str, game_logs: list[dict[str, Any]]) -> tuple[float, dict[str, Any] | None]:
    matches = [
        item
        for item in game_logs
        if item.get("opponent") == opponent_code
        and (item.get("playerId") == player.player_id or item.get("player", "").lower() == player.player.lower())
        and valid_batter_game_log_sample(item)
    ]
    matchup = None
    if matches:
        at_bats = sum(to_int(item.get("atBats")) for item in matches)
        hits = sum(to_int(item.get("hits")) for item in matches)
        matchup = {
            "playerId": player.player_id,
            "player": player.player,
            "opponent": opponent_code,
            "games": sum(to_int(item.get("games")) for item in matches),
            "atBats": at_bats,
            "hits": hits,
            "battingAverage": hits / at_bats if at_bats else 0.0,
            "sources": len({str(item.get("sourceId", "")) for item in matches if item.get("sourceId")}) or len(matches),
        }
    if not matchup or matchup.get("atBats", 0) < 5:
        return 0.0, matchup
    adjustment = clamp((matchup["battingAverage"] - player.batting_average) * 75, -10, 10)
    return adjustment, matchup


def pitching_game_log_summary(
    pitcher: dict[str, Any] | None,
    logs: list[dict[str, Any]],
    opponent_code: str = "",
) -> dict[str, Any] | None:
    if not pitcher:
        return None
    pitcher_id = str(pitcher.get("pitcherId", "")).strip()
    pitcher_name = str(pitcher.get("pitcher", "")).strip().lower()
    matches = [
        item
        for item in logs
        if (not opponent_code or item.get("opponent") == opponent_code)
        and ((pitcher_id and item.get("pitcherId") == pitcher_id) or (pitcher_name and item.get("pitcher", "").lower() == pitcher_name))
    ]
    if not matches and opponent_code:
        return pitching_game_log_summary(pitcher, logs, "")
    if not matches:
        return None

    innings = sum(to_float(item.get("innings")) for item in matches)
    games = sum(to_int(item.get("games")) for item in matches) or len(matches)
    batters_faced = sum(to_int(item.get("battersFaced")) for item in matches)
    strikeouts = sum(to_int(item.get("strikeouts")) for item in matches)
    walks = sum(to_int(item.get("walks")) for item in matches)
    hits_allowed = sum(to_int(item.get("hitsAllowed")) for item in matches)
    runs_allowed = sum(to_int(item.get("runsAllowed")) for item in matches)
    earned_runs = sum(to_int(item.get("earnedRuns")) for item in matches)
    home_runs_allowed = sum(to_int(item.get("homeRunsAllowed")) for item in matches)
    if not batters_faced and innings:
        batters_faced = int(round(innings * 4.25))

    return {
        "games": games,
        "innings": innings,
        "inningsPerGame": innings / games if games else 0.0,
        "battersFaced": batters_faced,
        "battersFacedPerGame": batters_faced / games if games else 0.0,
        "strikeouts": strikeouts,
        "strikeoutRate": strikeouts / batters_faced if batters_faced else 0.0,
        "walks": walks,
        "hitsAllowed": hits_allowed,
        "runsAllowed": runs_allowed,
        "earnedRuns": earned_runs,
        "homeRunsAllowed": home_runs_allowed,
        "era": earned_runs * 9 / innings if innings else 0.0,
        "whip": (walks + hits_allowed) / innings if innings else 0.0,
        "hitsPerNine": hits_allowed * 9 / innings if innings else 0.0,
        "opponent": opponent_code,
        "sources": len({str(item.get("sourceId", "")) for item in matches if item.get("sourceId")}) or len(matches),
    }


def pitching_game_log_adjustment(summary: dict[str, Any] | None) -> float:
    if not summary:
        return 0.0
    adjustment = 0.0
    if summary.get("hitsPerNine"):
        adjustment += (summary["hitsPerNine"] - 8.2) * 1.1
    if summary.get("whip"):
        adjustment += (summary["whip"] - 1.28) * 7
    if summary.get("era"):
        adjustment += (summary["era"] - 4.15) * 0.55
    if summary.get("strikeoutRate"):
        adjustment -= (summary["strikeoutRate"] - 0.225) * 16
    return clamp(adjustment, -8, 8)


def pitcher_adjustment(pitcher_key: str, pitchers: list[dict[str, Any]]) -> tuple[float, dict[str, Any] | None]:
    if not pitcher_key:
        return 0.0, None
    pitcher = next((item for item in pitchers if item.get("key") == pitcher_key), None)
    if not pitcher:
        return 0.0, None
    adjustment = 0.0
    if pitcher.get("battingAverageAllowed"):
        adjustment += (pitcher["battingAverageAllowed"] - 0.245) * 150
    if pitcher.get("opsAllowed"):
        adjustment += (pitcher["opsAllowed"] - 0.720) * 24
    if pitcher.get("hitsPerNine"):
        adjustment += (pitcher["hitsPerNine"] - 8.2) * 1.55
    if pitcher.get("whip"):
        adjustment += (pitcher["whip"] - 1.28) * 9
    if pitcher.get("era"):
        adjustment += (pitcher["era"] - 4.15) * 0.9
    if pitcher.get("eraMinus"):
        adjustment += (pitcher["eraMinus"] - 100) * 0.1
    if pitcher.get("fipMinus"):
        adjustment += (pitcher["fipMinus"] - 100) * 0.1
    if pitcher.get("kMinusBbRate"):
        adjustment -= (pitcher["kMinusBbRate"] - 0.145) * 20
    if pitcher.get("siera"):
        adjustment += (pitcher["siera"] - 4.15) * 0.8
    if pitcher.get("xfip"):
        adjustment += (pitcher["xfip"] - 4.15) * 0.6
    return clamp(adjustment, -18, 18), pitcher


def team_context_adjustment(opponent_code: str) -> tuple[float, dict[str, Any] | None]:
    team = next((item for item in load_team_batting() if item.get("team") == opponent_code), None)
    if not team:
        return 0.0, None
    # Opposing offense affects run environment more than hit skill, so keep this intentionally small.
    adjustment = 0.0
    if team.get("runsPerGame"):
        adjustment += (team["runsPerGame"] - 4.35) * 0.9
    if team.get("ops"):
        adjustment += (team["ops"] - 0.720) * 8
    return clamp(adjustment, -4, 4), team


def summarize_team_game_logs(logs: list[dict[str, Any]], label: str) -> dict[str, Any]:
    games = len(logs)
    wins = sum(1 for item in logs if item.get("win"))
    losses = sum(1 for item in logs if item.get("loss"))
    plate_appearances = sum(to_int(item.get("plateAppearances")) for item in logs)
    at_bats = sum(to_int(item.get("atBats")) for item in logs)
    hits = sum(to_int(item.get("hits")) for item in logs)
    total_bases = sum(to_int(item.get("totalBases")) for item in logs)
    runs_scored = sum(to_int(item.get("runsScored")) for item in logs)
    runs_allowed = sum(to_int(item.get("runsAllowed")) for item in logs)
    home_runs = sum(to_int(item.get("homeRuns")) for item in logs)
    walks = sum(to_int(item.get("walks")) for item in logs)
    strikeouts = sum(to_int(item.get("strikeouts")) for item in logs)
    on_base = (hits + walks) / plate_appearances if plate_appearances else 0.0
    slugging = total_bases / at_bats if at_bats else 0.0
    return {
        "label": label,
        "games": games,
        "wins": wins,
        "losses": losses,
        "winRate": round(wins / (wins + losses), 3) if wins + losses else 0.0,
        "runsPerGame": round(runs_scored / games, 2) if games else 0.0,
        "runsAllowedPerGame": round(runs_allowed / games, 2) if games else 0.0,
        "runDifferentialPerGame": round((runs_scored - runs_allowed) / games, 2) if games else 0.0,
        "plateAppearances": plate_appearances,
        "atBats": at_bats,
        "hits": hits,
        "hitsPerGame": round(hits / games, 2) if games else 0.0,
        "battingAverage": round(hits / at_bats, 3) if at_bats else 0.0,
        "onBase": round(on_base, 3),
        "slugging": round(slugging, 3),
        "ops": round(on_base + slugging, 3) if games else 0.0,
        "homeRuns": home_runs,
        "homeRunsPerGame": round(home_runs / games, 2) if games else 0.0,
        "walkRate": round(walks / plate_appearances, 3) if plate_appearances else 0.0,
        "strikeoutRate": round(strikeouts / plate_appearances, 3) if plate_appearances else 0.0,
    }


def team_matchup_summary(team_code: str, opponent_code: str) -> dict[str, Any]:
    team_code = normalize_team_code(team_code)
    opponent_code = normalize_team_code(opponent_code)
    logs = [
        item
        for item in load_team_game_logs()
        if item.get("team") == team_code and (not opponent_code or item.get("opponent") == opponent_code)
    ]
    all_team_logs = [item for item in load_team_game_logs() if item.get("team") == team_code]
    logs = sorted(logs, key=lambda item: parse_game_date(item.get("date")), reverse=True)
    all_team_logs = sorted(all_team_logs, key=lambda item: parse_game_date(item.get("date")), reverse=True)
    recent_pitchers = [
        {
            "date": item.get("date", ""),
            "opponent": item.get("opponent", ""),
            "opposingPitcher": item.get("opposingPitcher", ""),
            "result": item.get("result", ""),
            "runsScored": item.get("runsScored", 0),
            "runsAllowed": item.get("runsAllowed", 0),
            "ops": item.get("ops", 0.0),
        }
        for item in logs[:8]
    ]
    direct = summarize_team_game_logs(logs, f"{team_code} vs {opponent_code}") if logs else summarize_team_game_logs([], f"{team_code} vs {opponent_code}")
    overall = summarize_team_game_logs(all_team_logs, f"{team_code} overall")
    last5 = summarize_team_game_logs(logs[:5], f"Last 5 vs {opponent_code}") if logs else summarize_team_game_logs([], f"Last 5 vs {opponent_code}")
    return {
        "team": team_code,
        "teamName": TEAM_NAMES.get(team_code, team_code),
        "opponent": opponent_code,
        "opponentName": TEAM_NAMES.get(opponent_code, opponent_code),
        "available": bool(logs),
        "direct": direct,
        "overall": overall,
        "last5": last5,
        "recentPitchers": recent_pitchers,
        "note": (
            f"{len(logs)} saved team game log(s) for {team_code} vs {opponent_code}."
            if logs
            else f"No direct team game logs found for {team_code} vs {opponent_code}; showing season-level context when available."
        ),
    }


def team_game_log_adjustment(summary: dict[str, Any]) -> float:
    direct = summary.get("direct", {}) if summary else {}
    if not direct.get("games"):
        return 0.0
    adjustment = 0.0
    if direct.get("ops"):
        adjustment += (direct["ops"] - 0.720) * 12
    if direct.get("runsPerGame"):
        adjustment += (direct["runsPerGame"] - 4.35) * 0.7
    if direct.get("runDifferentialPerGame"):
        adjustment += direct["runDifferentialPerGame"] * 0.45
    if direct.get("winRate"):
        adjustment += (direct["winRate"] - 0.5) * 5
    return clamp(adjustment, -7, 7)


def same_player_record(record: dict[str, Any], name: str, player_id: str = "", role: str = "") -> bool:
    if role and str(record.get("role", "")).lower() != role.lower():
        return False
    ids = [player_id, str(player_id).removeprefix("mlb-")]
    return record_name_match(record, [name], ["player", "batter", "pitcher"]) or record_id_match(record, ids, ["playerId", "batterId", "pitcherId", "mlbId"])


def latest_statcast_quality(name: str, role: str, player_id: str = "") -> dict[str, Any]:
    rows = [row for row in load_statcast_quality() if same_player_record(row, name, player_id, role)]
    return max(rows, key=lambda row: (to_int(row.get("season")), parse_game_date(row.get("endDate"))), default={})


def rolling_form_map(name: str, role: str, player_id: str = "") -> dict[int, dict[str, Any]]:
    rows = [row for row in load_rolling_form() if same_player_record(row, name, player_id, role)]
    latest: dict[int, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: to_int(item.get("season"))):
        latest[to_int(row.get("windowDays"))] = row
    return latest


def split_for_hand(name: str, role: str, hand: str, player_id: str = "") -> dict[str, Any]:
    normalized_hand = str(hand or "").strip().upper()[:1]
    if not normalized_hand:
        return {}
    rows = [
        row
        for row in load_handedness_splits()
        if same_player_record(row, name, player_id, role) and str(row.get("split", "")).upper()[:1] == normalized_hand
    ]
    return max(rows, key=lambda row: (to_int(row.get("season")), to_int(row.get("plateAppearances"))), default={})


def player_quality_adjustment(quality: dict[str, Any], role: str) -> float:
    if not quality:
        return 0.0
    if role == "pitcher":
        adjustment = 0.0
        if quality.get("xwoba"):
            adjustment += (0.320 - quality["xwoba"]) * 18
        if quality.get("barrelRate"):
            adjustment += (0.075 - quality["barrelRate"]) * 12
        if quality.get("hardHitRate"):
            adjustment += (0.38 - quality["hardHitRate"]) * 4
        if quality.get("strikeoutRate"):
            adjustment += (quality["strikeoutRate"] - 0.225) * 10
        return clamp(adjustment, -5.5, 5.5)
    adjustment = 0.0
    if quality.get("xwoba"):
        adjustment += (quality["xwoba"] - 0.320) * 18
    if quality.get("xba"):
        adjustment += (quality["xba"] - 0.245) * 9
    if quality.get("xslg"):
        adjustment += (quality["xslg"] - 0.410) * 7
    if quality.get("barrelRate"):
        adjustment += (quality["barrelRate"] - 0.075) * 15
    if quality.get("hardHitRate"):
        adjustment += (quality["hardHitRate"] - 0.38) * 4
    return clamp(adjustment, -6.5, 6.5)


def rolling_form_adjustment(rolling: dict[int, dict[str, Any]], target: str = "hitting") -> float:
    if not rolling:
        return 0.0
    weights = {7: 0.48, 14: 0.32, 30: 0.20}
    adjustment = 0.0
    total_weight = 0.0
    for days, weight in weights.items():
        row = rolling.get(days)
        if not row or to_int(row.get("plateAppearances")) < 6:
            continue
        if target == "pitching":
            score = 0.0
            if row.get("xwoba"):
                score += (0.320 - row["xwoba"]) * 14
            if row.get("strikeoutRate"):
                score += (row["strikeoutRate"] - 0.225) * 11
            if row.get("barrelRate"):
                score += (0.075 - row["barrelRate"]) * 10
        else:
            score = 0.0
            if row.get("xwoba"):
                score += (row["xwoba"] - 0.320) * 12
            if row.get("battingAverage"):
                score += (row["battingAverage"] - 0.245) * 7
            if row.get("barrelRate"):
                score += (row["barrelRate"] - 0.075) * 13
            if row.get("hardHitRate"):
                score += (row["hardHitRate"] - 0.38) * 3
        adjustment += score * weight
        total_weight += weight
    return clamp(adjustment / total_weight if total_weight else 0.0, -5.5, 5.5)


def handedness_adjustment(split: dict[str, Any], role: str) -> float:
    if not split or to_int(split.get("plateAppearances")) < 10:
        return 0.0
    if role == "pitcher":
        adjustment = 0.0
        if split.get("xwoba"):
            adjustment += (0.320 - split["xwoba"]) * 11
        if split.get("strikeoutRate"):
            adjustment += (split["strikeoutRate"] - 0.225) * 8
        if split.get("barrelRate"):
            adjustment += (0.075 - split["barrelRate"]) * 8
        return clamp(adjustment, -4, 4)
    adjustment = 0.0
    if split.get("xwoba"):
        adjustment += (split["xwoba"] - 0.320) * 11
    if split.get("battingAverage"):
        adjustment += (split["battingAverage"] - 0.245) * 6
    if split.get("barrelRate"):
        adjustment += (split["barrelRate"] - 0.075) * 10
    if split.get("strikeoutRate"):
        adjustment -= (split["strikeoutRate"] - 0.225) * 5
    return clamp(adjustment, -4, 4)


def pitcher_throw_hand(pitcher: dict[str, Any] | None) -> str:
    if not pitcher:
        return ""
    for field in ["throws", "pitchHand", "throwingHand", "handedness", "pThrows"]:
        hand = str(pitcher.get(field, "")).strip().upper()[:1]
        if hand in {"L", "R"}:
            return hand
    name = str(pitcher.get("pitcher", "")).lower()
    if any(token in name for token in ["fried", "skubal", "sale", "snell"]):
        return "L"
    return ""


def advanced_batter_context(player: Player, pitcher: dict[str, Any] | None) -> dict[str, Any]:
    quality = latest_statcast_quality(player.player, "batter", player.player_id)
    rolling = rolling_form_map(player.player, "batter", player.player_id)
    hand = pitcher_throw_hand(pitcher)
    split = split_for_hand(player.player, "batter", hand, player.player_id) if hand else {}
    quality_adj = player_quality_adjustment(quality, "batter")
    rolling_adj = rolling_form_adjustment(rolling)
    handed_adj = handedness_adjustment(split, "batter")
    return {
        "quality": quality,
        "rolling": rolling,
        "handedness": split,
        "pitcherHand": hand,
        "qualityAdjustment": round(quality_adj, 2),
        "rollingAdjustment": round(rolling_adj, 2),
        "handednessAdjustment": round(handed_adj, 2),
        "totalAdjustment": round(clamp(quality_adj + rolling_adj + handed_adj, -10, 10), 2),
    }


def advanced_pitcher_context(pitcher: dict[str, Any] | None) -> dict[str, Any]:
    if not pitcher:
        return {}
    name = str(pitcher.get("pitcher", ""))
    pitcher_id = str(pitcher.get("pitcherId", ""))
    quality = latest_statcast_quality(name, "pitcher", pitcher_id)
    rolling = rolling_form_map(name, "pitcher", pitcher_id)
    quality_adj = player_quality_adjustment(quality, "pitcher")
    rolling_adj = rolling_form_adjustment(rolling, "pitching")
    return {
        "quality": quality,
        "rolling": rolling,
        "qualityAdjustment": round(quality_adj, 2),
        "rollingAdjustment": round(rolling_adj, 2),
        "totalAdjustment": round(clamp(quality_adj + rolling_adj, -8, 8), 2),
    }


def context_teams(record: dict[str, Any]) -> set[str]:
    return {
        normalize_team_code(str(value))
        for value in [
            record.get("homeTeam", ""),
            record.get("awayTeam", ""),
            nested_get(record, ["home", "team", "abbreviation"], ""),
            nested_get(record, ["away", "team", "abbreviation"], ""),
        ]
        if normalize_team_code(str(value))
    }


def parse_context_date(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return parse_game_date(text[:10])


def find_ballpark_context(team_code: str, opponent_code: str, date: str = "") -> dict[str, Any]:
    selected = normalize_team_code(team_code)
    opponent = normalize_team_code(opponent_code)
    target_date = parse_game_date(date).date() if date else None
    candidates = []
    for record in [*load_ballpark_context(), *load_game_context()]:
        teams = context_teams(record)
        if selected and selected not in teams:
            continue
        if opponent and opponent not in teams:
            continue
        record_date = parse_context_date(record.get("date"))
        if target_date and record_date != datetime.min and record_date.date() != target_date:
            continue
        candidates.append(record)
    return max(candidates, key=lambda item: parse_context_date(item.get("date")), default={})


def environment_factor(context: dict[str, Any], target: str) -> float:
    if not context:
        return 1.0
    base = normalize_factor(context.get("parkFactor") or context.get("runFactor"), 1.0)
    if target == "homeRuns":
        base = normalize_factor(context.get("homeRunFactor"), base)
    elif target in {"hits", "totalBases", "pitcherHitsAllowed"}:
        base = normalize_factor(context.get("hitFactor"), base)

    roof = str(context.get("roof", "")).lower()
    roof_closed = any(token in roof for token in ["closed", "dome", "retractable closed"])
    temp = to_float(context.get("temperature"))
    wind_mph = to_float(context.get("windMph"))
    direction = str(context.get("windDirection", "")).lower()

    weather_factor = 1.0
    if not roof_closed:
        if temp:
            if target == "homeRuns":
                weather_factor += clamp((temp - 70) / 1000, -0.035, 0.045)
            else:
                weather_factor += clamp((temp - 70) / 1500, -0.022, 0.028)
        if wind_mph:
            if any(token in direction for token in ["out", "carry", "toward", "to lf", "to rf", "center"]):
                weather_factor += clamp(wind_mph / (450 if target == "homeRuns" else 700), 0.0, 0.045 if target == "homeRuns" else 0.026)
            elif any(token in direction for token in ["in", "from", "blowing in"]):
                weather_factor -= clamp(wind_mph / (420 if target == "homeRuns" else 650), 0.0, 0.05 if target == "homeRuns" else 0.028)
            elif any(token in direction for token in ["left", "right", "cross"]):
                weather_factor += 0.004 if target in {"hits", "totalBases"} else 0.0
    return clamp(base * weather_factor, 0.82, 1.22)


def ballpark_environment_context(team_code: str, opponent_code: str, date: str = "") -> dict[str, Any]:
    context = find_ballpark_context(team_code, opponent_code, date)
    if not context:
        return {
            "available": False,
            "hitFactor": 1.0,
            "homeRunFactor": 1.0,
            "runFactor": 1.0,
            "strikeoutFactor": 1.0,
            "adjustment": 0.0,
        }
    hit_factor = environment_factor(context, "hits")
    hr_factor = environment_factor(context, "homeRuns")
    run_factor = environment_factor(context, "runs")
    strikeout_factor = clamp(1 - ((run_factor - 1) * 0.22), 0.96, 1.04)
    return {
        "available": True,
        "source": context.get("source", ""),
        "date": context.get("date", ""),
        "game": context.get("game", ""),
        "venue": context.get("venue", ""),
        "city": context.get("city", ""),
        "weather": context.get("weather", ""),
        "temperature": to_float(context.get("temperature")),
        "windMph": to_float(context.get("windMph")),
        "windDirection": context.get("windDirection", ""),
        "roof": context.get("roof", ""),
        "parkFactor": round(normalize_factor(context.get("parkFactor") or context.get("runFactor"), 1.0), 3),
        "hitFactor": round(hit_factor, 3),
        "homeRunFactor": round(hr_factor, 3),
        "runFactor": round(run_factor, 3),
        "strikeoutFactor": round(strikeout_factor, 3),
        "adjustment": round((run_factor - 1) * 100, 1),
    }


def parse_game_date(value: Any) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.min


def game_log_entries_for_player(player: Player, game_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(game_logs):
        same_player = item.get("playerId") == player.player_id or item.get("player", "").lower() == player.player.lower()
        if not same_player:
            continue
        if item.get("entries"):
            for entry in item.get("entries", []):
                normalized = {
                    "date": entry.get("date", ""),
                    "opponent": normalize_team_code(str(entry.get("opponent") or item.get("opponent") or "")),
                    "games": 1,
                    "plateAppearances": to_int(entry.get("plateAppearances")),
                    "atBats": to_int(entry.get("atBats")),
                    "hits": to_int(entry.get("hits")),
                    "homeRuns": to_int(entry.get("homeRuns")),
                    "walks": to_int(entry.get("walks")),
                    "strikeouts": to_int(entry.get("strikeouts")),
                    "totalBases": to_int(entry.get("totalBases"), to_int(entry.get("hits"))),
                    "_order": index,
                }
                if valid_batter_game_log_sample(normalized):
                    entries.append(normalized)
            continue

        normalized = {
            "date": item.get("date", ""),
            "opponent": normalize_team_code(str(item.get("opponent", ""))),
            "games": to_int(item.get("games"), 1),
            "plateAppearances": to_int(item.get("plateAppearances")),
            "atBats": to_int(item.get("atBats")),
            "hits": to_int(item.get("hits")),
            "homeRuns": to_int(item.get("homeRuns")),
            "walks": to_int(item.get("walks")),
            "strikeouts": to_int(item.get("strikeouts")),
            "totalBases": to_int(item.get("totalBases"), to_int(item.get("hits"))),
            "_order": index,
        }
        if valid_batter_game_log_sample(normalized):
            entries.append(normalized)
    return sorted(entries, key=lambda entry: (parse_game_date(entry.get("date")), entry.get("_order", 0)), reverse=True)


def summarize_batter_entries(entries: list[dict[str, Any]], limit: int, label: str) -> dict[str, Any]:
    selected = entries[:limit]
    games = sum(max(to_int(entry.get("games"), 1), 1) for entry in selected)
    plate_appearances = sum(to_int(entry.get("plateAppearances")) for entry in selected)
    at_bats = sum(to_int(entry.get("atBats")) for entry in selected)
    hits = sum(to_int(entry.get("hits")) for entry in selected)
    home_runs = sum(to_int(entry.get("homeRuns")) for entry in selected)
    walks = sum(to_int(entry.get("walks")) for entry in selected)
    strikeouts = sum(to_int(entry.get("strikeouts")) for entry in selected)
    total_bases = sum(to_int(entry.get("totalBases")) for entry in selected)
    return {
        "label": label,
        "games": games,
        "plateAppearances": plate_appearances,
        "atBats": at_bats,
        "hits": hits,
        "homeRuns": home_runs,
        "walks": walks,
        "strikeouts": strikeouts,
        "totalBases": total_bases,
        "battingAverage": round(hits / at_bats, 3) if at_bats else 0.0,
        "slugging": round(total_bases / at_bats, 3) if at_bats else 0.0,
        "hitRate": round(hits / games, 2) if games else 0.0,
        "homeRunRate": round(home_runs / max(plate_appearances, at_bats, 1), 3) if selected else 0.0,
        "strikeoutRate": round(strikeouts / max(plate_appearances, at_bats, 1), 3) if selected else 0.0,
    }


def batter_recent_form(player: Player, opponent_code: str, game_logs: list[dict[str, Any]]) -> dict[str, Any]:
    entries = game_log_entries_for_player(player, game_logs)
    opponent_entries = [entry for entry in entries if entry.get("opponent") == opponent_code]
    return {
        "available": bool(entries),
        "opponent": opponent_code,
        "last5": summarize_batter_entries(entries, 5, "Last 5"),
        "last10": summarize_batter_entries(entries, 10, "Last 10"),
        "last5VsOpponent": summarize_batter_entries(opponent_entries, 5, f"Last 5 vs {opponent_code or 'opponent'}"),
        "last5Entries": public_game_log_entries(entries[:5]),
        "last10Entries": public_game_log_entries(entries[:10]),
        "last5VsOpponentEntries": public_game_log_entries(opponent_entries[:5]),
    }


def public_game_log_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "date": entry.get("date", ""),
            "opponent": entry.get("opponent", ""),
            "plateAppearances": to_int(entry.get("plateAppearances")),
            "atBats": to_int(entry.get("atBats")),
            "hits": to_int(entry.get("hits")),
            "homeRuns": to_int(entry.get("homeRuns")),
            "walks": to_int(entry.get("walks")),
            "strikeouts": to_int(entry.get("strikeouts")),
            "totalBases": to_int(entry.get("totalBases")),
        }
        for entry in entries
    ]


def player_recent_payload(player_id: str, opponent_code: str) -> dict[str, Any]:
    player = selected_player_by_id(player_id)
    if not player:
        raise ValueError("Player not found.")
    opponent = normalize_team_code(opponent_code)
    return {"player": asdict(player), "recent": batter_recent_form(player, opponent, load_game_logs())}


def batter_home_run_profile(player: Player, context: dict[str, Any]) -> dict[str, Any]:
    plate_appearances = max(player.plate_appearances, 0)
    at_bats = max(player.at_bats, 0)
    home_runs = max(player.home_runs, 0)
    exact_matchup = context["opponent"].get("batterPitcher") or {}
    pitcher = context["opponent"].get("pitcher") or {}
    team_pitching = context["opponent"].get("teamPitching") or {}
    standard = team_pitching.get("standardPitching") or {}
    allowed_home_runs = pitcher.get("homeRunsAllowed") or standard.get("homeRunsAllowed") or 0
    allowed_bf = pitcher.get("battersFaced") or (standard.get("innings", 0) * 4.25 if standard.get("innings") else 0)
    return {
        "homeRuns": home_runs,
        "homeRunsPerGame": round(home_runs / player.games, 2) if player.games else 0.0,
        "homeRunRate": round(home_runs / plate_appearances, 3) if plate_appearances else 0.0,
        "atBatsPerHomeRun": round(at_bats / home_runs, 1) if home_runs else 0.0,
        "plateAppearancesPerHomeRun": round(plate_appearances / home_runs, 1) if home_runs else 0.0,
        "slugging": round(player.slugging or (player.total_bases / at_bats if at_bats else 0.0), 3),
        "matchupHomeRuns": exact_matchup.get("homeRuns", 0),
        "matchupBarrelRate": round(exact_matchup.get("barrelRate", 0.0), 3),
        "allowedHomeRunRate": round(allowed_home_runs / allowed_bf, 3) if allowed_bf else 0.0,
    }


def rate_per_nine(count: float, innings: float) -> float:
    return count * 9 / innings if innings else 0.0


def pitcher_walk_rate(pitcher: dict[str, Any]) -> float:
    if pitcher.get("walkRate"):
        return clamp(pitcher["walkRate"], 0.015, 0.22)
    if pitcher.get("walks") and pitcher.get("battersFaced"):
        return clamp(pitcher["walks"] / pitcher["battersFaced"], 0.015, 0.22)
    if pitcher.get("walks") and pitcher.get("plateAppearances"):
        return clamp(pitcher["walks"] / pitcher["plateAppearances"], 0.015, 0.22)
    if pitcher.get("walks") and pitcher.get("innings"):
        return clamp(pitcher["walks"] / (pitcher["innings"] * 4.25), 0.015, 0.22)
    return 0.085


def pitcher_profile(pitcher: dict[str, Any] | None, pitcher_game_log: dict[str, Any] | None = None) -> dict[str, Any]:
    if not pitcher:
        return {}
    innings = to_float(pitcher.get("innings"))
    games = to_int(pitcher.get("games"))
    starts = to_int(pitcher.get("gamesStarted"))
    appearances = starts or games or 0
    strikeouts = to_int(pitcher.get("strikeouts"))
    walks = to_int(pitcher.get("walks"))
    home_runs = to_int(pitcher.get("homeRunsAllowed"))
    hits = to_int(pitcher.get("hitsAllowed"))
    runs = to_int(pitcher.get("runsAllowed")) or to_int(pitcher.get("earnedRuns"))
    innings_per_outing, batters_per_outing = pitcher_workload(pitcher)
    return {
        "pitcher": pitcher.get("pitcher", ""),
        "team": pitcher.get("team", ""),
        "games": games,
        "gamesStarted": starts,
        "innings": round(innings, 1),
        "inningsPerOuting": round(innings_per_outing, 2),
        "battersFacedPerOuting": round(batters_per_outing, 1),
        "era": round(to_float(pitcher.get("era")), 2),
        "fip": round(to_float(pitcher.get("fip") or pitcher.get("xfip")), 2),
        "whip": round(to_float(pitcher.get("whip")), 3),
        "strikeoutRate": round(pitcher_strikeout_rate(pitcher), 3),
        "walkRate": round(pitcher_walk_rate(pitcher), 3),
        "strikeoutsPerNine": round(rate_per_nine(strikeouts, innings), 2),
        "walksPerNine": round(rate_per_nine(walks, innings), 2),
        "homeRunsPerNine": round(rate_per_nine(home_runs, innings), 2),
        "hitsPerNine": round(to_float(pitcher.get("hitsPerNine")) or rate_per_nine(hits, innings), 2),
        "strikeoutsPerGame": round(strikeouts / appearances, 2) if appearances else 0.0,
        "walksPerGame": round(walks / appearances, 2) if appearances else 0.0,
        "runsAllowedPerGame": round(runs / appearances, 2) if appearances else 0.0,
        "recentVsOpponent": pitcher_game_log or {},
    }


def batter_pitcher_matchup(player: Player, pitcher: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pitcher:
        return None
    pitcher_id = pitcher.get("pitcherId", "")
    pitcher_name = pitcher.get("pitcher", "").lower()
    for matchup in load_batter_pitcher_advanced():
        batter_match = matchup.get("batterId") == player.player_id or matchup.get("batter", "").lower() == player.player.lower()
        pitcher_match = (pitcher_id and matchup.get("pitcherId") == pitcher_id) or matchup.get("pitcher", "").lower() == pitcher_name
        if batter_match and pitcher_match:
            return matchup
    return None


def blend_rate(base: float, matchup_rate: float, opportunities: int, max_weight: float = 0.38) -> float:
    if not matchup_rate or opportunities <= 0:
        return base
    weight = clamp(opportunities / 30, 0.0, max_weight)
    return base * (1 - weight) + matchup_rate * weight


def probability_at_least(expected: float, count: int) -> float:
    if count <= 0:
        return 1.0
    cumulative = 0.0
    for index in range(count):
        cumulative += math.exp(-expected) * math.pow(expected, index) / math.factorial(index)
    return clamp(1 - cumulative, 0.0, 1.0)


def over_threshold(line: float) -> int:
    return max(int(math.floor(line)) + 1, 0)


def american_to_implied(odds: int) -> float:
    if odds == 0:
        odds = -110
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def american_profit_per_unit(odds: int) -> float:
    if odds == 0:
        odds = -110
    if odds > 0:
        return odds / 100
    return 100 / abs(odds)


def fair_american(probability: float) -> int:
    probability = clamp(probability, 0.001, 0.999)
    if probability >= 0.5:
        return int(round(-(probability / (1 - probability)) * 100))
    return int(round(((1 - probability) / probability) * 100))


def market_view(probability: float, line: float, odds: int) -> dict[str, Any]:
    if odds == 0:
        odds = -110
    implied = american_to_implied(odds)
    profit = american_profit_per_unit(odds)
    expected_value = probability * profit - (1 - probability)
    edge = probability - implied
    if edge >= 0.045 and expected_value > 0:
        verdict = "Positive value"
    elif edge >= 0.015 and expected_value > 0:
        verdict = "Thin value"
    elif edge <= -0.025:
        verdict = "No value"
    else:
        verdict = "Fair price"
    return {
        "line": round(line, 1),
        "odds": odds,
        "impliedProbability": round(implied, 3),
        "modelProbability": round(probability, 3),
        "edge": round(edge, 3),
        "expectedValuePerUnit": round(expected_value, 3),
        "fairAmerican": fair_american(probability),
        "verdict": verdict,
    }


def attach_market(prediction: dict[str, Any], line: float, odds: int, unit_label: str) -> dict[str, Any]:
    threshold = over_threshold(line)
    probability = probability_at_least(prediction["expected"], threshold)
    market = market_view(probability, line, odds)
    prediction.update(
        {
            "line": round(line, 1),
            "overThreshold": threshold,
            "probabilityOverLine": round(probability, 3),
            "market": market,
            "cards": [
                {"label": f"Over {line:g} {unit_label}", "value": round(probability, 3), "format": "percent"},
                {"label": f"Expected {unit_label}", "value": prediction["expected"], "format": "number"},
                {"label": "Model edge", "value": market["edge"], "format": "percent"},
            ],
        }
    )
    return prediction


class GitHubApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class EspnApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class MlbStatsApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def split_repo_name(value: str) -> tuple[str, str]:
    text = value.strip().removeprefix("https://github.com/").strip("/")
    if "/" not in text:
        return "", ""
    owner, repo = text.split("/", 1)
    return owner.strip(), repo.strip().split("/")[0]


def github_api_get(path: str) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "baseball-prop-predictor",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(f"{GITHUB_API_BASE}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                payload["_rateLimitRemaining"] = response.headers.get("X-RateLimit-Remaining")
            return payload
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
            message = payload.get("message", raw)
        except json.JSONDecodeError:
            message = raw or str(error)
        raise GitHubApiError(error.code, message) from error
    except urllib.error.URLError as error:
        raise GitHubApiError(503, f"Could not reach GitHub API: {error.reason}") from error


def github_repo_status(owner: str, repo: str) -> dict[str, Any]:
    if not owner or not repo:
        configured = os.environ.get("GITHUB_REPOSITORY", "")
        owner, repo = split_repo_name(configured)
    if not owner or not repo:
        raise GitHubApiError(400, "Provide a repository as owner/repo or set GITHUB_REPOSITORY.")

    repository = github_api_get(f"/repos/{owner}/{repo}")
    runs_payload = github_api_get(f"/repos/{owner}/{repo}/actions/runs?per_page=5")
    runs = runs_payload.get("workflow_runs", []) if isinstance(runs_payload, dict) else []
    return {
        "authenticated": bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")),
        "rateLimitRemaining": repository.get("_rateLimitRemaining") or runs_payload.get("_rateLimitRemaining"),
        "repository": {
            "fullName": repository.get("full_name"),
            "description": repository.get("description"),
            "url": repository.get("html_url"),
            "defaultBranch": repository.get("default_branch"),
            "visibility": repository.get("visibility"),
            "language": repository.get("language"),
            "stars": repository.get("stargazers_count"),
            "forks": repository.get("forks_count"),
            "openIssues": repository.get("open_issues_count"),
            "updatedAt": repository.get("updated_at"),
            "pushedAt": repository.get("pushed_at"),
        },
        "workflowRuns": [
            {
                "name": run.get("name") or run.get("display_title") or "Workflow",
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "event": run.get("event"),
                "branch": run.get("head_branch"),
                "commitSha": (run.get("head_sha") or "")[:7],
                "url": run.get("html_url"),
                "createdAt": run.get("created_at"),
                "updatedAt": run.get("updated_at"),
            }
            for run in runs
        ],
    }


def espn_api_get(resource: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    query = urlencode({key: value for key, value in (params or {}).items() if value})
    url = f"{ESPN_MLB_API_BASE}{resource}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "baseball-prop-predictor",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
            message = payload.get("message") or payload.get("error") or raw
        except json.JSONDecodeError:
            message = raw or str(error)
        raise EspnApiError(error.code, f"ESPN API error: {message}") from error
    except urllib.error.URLError as error:
        raise EspnApiError(503, f"Could not reach ESPN API: {error.reason}") from error


def espn_logo(team: dict[str, Any]) -> str:
    logos = team.get("logos") or []
    if logos and isinstance(logos[0], dict):
        return logos[0].get("href", "")
    return team.get("logo", "")


def espn_link(team: dict[str, Any], rel_name: str = "clubhouse") -> str:
    for link in team.get("links", []) or []:
        rels = link.get("rel") or []
        if rel_name in rels:
            return link.get("href", "")
    return ""


def normalize_espn_team(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(team.get("id", "")),
        "uid": team.get("uid", ""),
        "slug": team.get("slug", ""),
        "abbreviation": team.get("abbreviation", ""),
        "displayName": team.get("displayName", ""),
        "shortDisplayName": team.get("shortDisplayName", ""),
        "location": team.get("location", ""),
        "name": team.get("name", ""),
        "color": team.get("color", ""),
        "alternateColor": team.get("alternateColor", ""),
        "logo": espn_logo(team),
        "clubhouse": espn_link(team),
        "isActive": bool(team.get("isActive", True)),
    }


def espn_team_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if isinstance(payload.get("team"), dict):
        entries.append(payload["team"])
    for entry in payload.get("teams", []) or []:
        team = entry.get("team", entry) if isinstance(entry, dict) else {}
        if isinstance(team, dict):
            entries.append(team)
    for sport in payload.get("sports", []) or []:
        for league in sport.get("leagues", []) or []:
            for entry in league.get("teams", []) or []:
                team = entry.get("team", entry) if isinstance(entry, dict) else {}
                if isinstance(team, dict):
                    entries.append(team)
    return entries


def espn_teams() -> dict[str, Any]:
    payload = espn_api_get("/teams")
    teams = [normalize_espn_team(team) for team in espn_team_entries(payload)]
    teams = sorted(teams, key=lambda item: item["displayName"])
    return {
        "source": "ESPN Site API",
        "endpoint": f"{ESPN_MLB_API_BASE}/teams",
        "count": len(teams),
        "teams": teams,
    }


def espn_team_lookup(team_key: str) -> dict[str, Any]:
    key = team_key.strip().lower()
    if not key:
        raise EspnApiError(400, "Enter an ESPN team id or abbreviation.")

    direct_error = ""
    try:
        direct_payload = espn_api_get(f"/teams/{quote(team_key.strip())}")
        direct_teams = [normalize_espn_team(team) for team in espn_team_entries(direct_payload)]
        if direct_teams:
            return {
                "source": "ESPN Site API",
                "endpoint": f"{ESPN_MLB_API_BASE}/teams/{team_key.strip()}",
                "team": direct_teams[0],
                "fallbackUsed": False,
            }
    except EspnApiError as error:
        direct_error = error.message

    teams_payload = espn_teams()
    for team in teams_payload["teams"]:
        candidates = {
            team.get("id", "").lower(),
            team.get("abbreviation", "").lower(),
            team.get("slug", "").lower(),
            team.get("displayName", "").lower(),
            team.get("shortDisplayName", "").lower(),
            team.get("name", "").lower(),
        }
        if key in candidates:
            return {
                "source": "ESPN Site API",
                "endpoint": f"{ESPN_MLB_API_BASE}/teams",
                "team": team,
                "fallbackUsed": True,
                "directEndpointError": direct_error,
            }
    raise EspnApiError(404, f"No ESPN MLB team found for {team_key}.")


def espn_stat_value(competitor: dict[str, Any], target: str) -> str:
    target_lower = target.lower()
    for stat in competitor.get("statistics", []) or []:
        names = {str(stat.get("name", "")).lower(), str(stat.get("abbreviation", "")).lower()}
        if target_lower in names:
            return str(stat.get("displayValue", ""))
    return ""


def espn_probable_starter(competitor: dict[str, Any]) -> dict[str, Any] | None:
    for item in competitor.get("probables", []) or []:
        if item.get("name") == "probableStartingPitcher":
            athlete = item.get("athlete", {}) or {}
            return {
                "id": str(item.get("playerId") or athlete.get("id") or ""),
                "name": athlete.get("displayName") or athlete.get("fullName") or "",
                "record": item.get("record", ""),
                "position": athlete.get("position", ""),
            }
    return None


def normalize_espn_competitor(competitor: dict[str, Any]) -> dict[str, Any]:
    team = normalize_espn_team(competitor.get("team", {}) or {})
    return {
        "homeAway": competitor.get("homeAway", ""),
        "winner": competitor.get("winner"),
        "score": to_int(competitor.get("score")),
        "team": team,
        "hits": to_int(espn_stat_value(competitor, "hits")),
        "errors": to_int(espn_stat_value(competitor, "errors")),
        "record": next(
            (record.get("summary", "") for record in competitor.get("records", []) or [] if record.get("name") == "overall"),
            "",
        ),
        "probableStarter": espn_probable_starter(competitor),
    }


def normalize_espn_event(event: dict[str, Any]) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = [normalize_espn_competitor(item) for item in competition.get("competitors", []) or []]
    home = next((item for item in competitors if item["homeAway"] == "home"), None)
    away = next((item for item in competitors if item["homeAway"] == "away"), None)
    status_type = nested_get(competition, ["status", "type"], {}) or nested_get(event, ["status", "type"], {}) or {}
    venue = competition.get("venue", {}) or {}
    return {
        "id": str(event.get("id", "")),
        "name": event.get("name", ""),
        "shortName": event.get("shortName", ""),
        "date": event.get("date", ""),
        "venue": venue.get("fullName", ""),
        "city": nested_get(venue, ["address", "city"], ""),
        "status": {
            "state": status_type.get("state", ""),
            "detail": status_type.get("detail") or status_type.get("description", ""),
            "completed": bool(status_type.get("completed")),
        },
        "home": home,
        "away": away,
    }


def espn_scoreboard(params: dict[str, str]) -> dict[str, Any]:
    allowed = {key: value for key, value in params.items() if key in {"dates", "limit", "groups", "seasontype"}}
    payload = espn_api_get("/scoreboard", allowed)
    events = [normalize_espn_event(event) for event in payload.get("events", []) or []]
    return {
        "source": "ESPN Site API",
        "endpoint": f"{ESPN_MLB_API_BASE}/scoreboard",
        "season": payload.get("season", {}),
        "day": payload.get("day", {}),
        "count": len(events),
        "events": events,
    }


def current_season() -> int:
    return 2026


def mlb_client() -> Any:
    try:
        import mlbstatsapi  # type: ignore
    except ImportError as error:
        raise MlbStatsApiError(
            503,
            "python-mlb-statsapi is not installed. Run: python -m pip install -r requirements.txt",
        ) from error
    return mlbstatsapi.Mlb()


def public_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return {key: public_model(item) for key, item in vars(value).items() if not key.startswith("_")}
    if isinstance(value, list):
        return [public_model(item) for item in value]
    if isinstance(value, tuple):
        return [public_model(item) for item in value]
    if isinstance(value, dict):
        return {key: public_model(item) for key, item in value.items()}
    return value


def nested_get(payload: Any, path: list[str], default: Any = None) -> Any:
    current = payload
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
        if current is None:
            return default
    return current


def stat_from_splits(stats_payload: Any, group: str, stat_type: str) -> dict[str, Any]:
    payload = public_model(stats_payload)
    splits = nested_get(payload, [group, stat_type, "splits"], [])
    if isinstance(splits, list) and splits:
        stat = splits[0].get("stat", {}) if isinstance(splits[0], dict) else {}
        return stat if isinstance(stat, dict) else {}
    return {}


def safe_stat_number(stats: dict[str, Any], names: list[str]) -> float:
    for name in names:
        if name in stats:
            return to_float(stats.get(name))
    return 0.0


def safe_stat_int(stats: dict[str, Any], names: list[str]) -> int:
    for name in names:
        if name in stats:
            return to_int(stats.get(name))
    return 0


def person_hand_code(person: dict[str, Any], hand_type: str) -> str:
    candidates = [
        nested_get(person, [hand_type, "code"], ""),
        nested_get(person, [hand_type, "description"], ""),
        nested_get(person, [hand_type.lower(), "code"], ""),
        nested_get(person, [hand_type.lower(), "description"], ""),
        nested_get(person, [hand_type.lower().replace("_", ""), "code"], ""),
        nested_get(person, [hand_type.lower().replace("_", ""), "description"], ""),
        nested_get(person, [hand_type.replace("Hand", "_hand"), "code"], ""),
    ]
    for value in candidates:
        hand = str(value or "").strip().upper()[:1]
        if hand in {"L", "R", "S"}:
            return hand
    return ""


def mlb_statsapi_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = urlencode({key: value for key, value in (params or {}).items() if value not in {"", None}})
    url = f"{MLB_STATS_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise MlbStatsApiError(error.code, raw or str(error)) from error
    except urllib.error.URLError as error:
        raise MlbStatsApiError(503, f"Could not reach MLB StatsAPI: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise MlbStatsApiError(502, "MLB StatsAPI returned a non-JSON response.") from error
    return payload if isinstance(payload, dict) else {}


def mlb_game_log_splits(player_id: int, group: str, season: int) -> list[dict[str, Any]]:
    payload = mlb_statsapi_get(
        f"/people/{player_id}/stats",
        {"stats": "gameLog", "group": group, "season": season, "sportId": 1},
    )
    for stat_block in payload.get("stats", []) or []:
        splits = stat_block.get("splits", []) if isinstance(stat_block, dict) else []
        if splits:
            return [split for split in splits if isinstance(split, dict)]
    return []


def split_opponent_code(split: dict[str, Any]) -> str:
    opponent = split.get("opponent") or {}
    if isinstance(opponent, dict):
        return normalize_team_code(str(opponent.get("abbreviation") or opponent.get("teamCode") or opponent.get("name") or ""))
    return normalize_team_code(str(opponent))


def batter_game_log_entries_from_splits(splits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    for split in splits:
        stat = split.get("stat", {}) if isinstance(split.get("stat"), dict) else {}
        at_bats = safe_stat_int(stat, ["atBats", "at_bats"])
        hits = safe_stat_int(stat, ["hits"])
        walks = safe_stat_int(stat, ["baseOnBalls", "base_on_balls", "walks"])
        hit_by_pitch = safe_stat_int(stat, ["hitByPitch", "hit_by_pitch"])
        sacrifice_flies = safe_stat_int(stat, ["sacFlies", "sac_flies"])
        plate_appearances = safe_stat_int(stat, ["plateAppearances", "plate_appearances"]) or at_bats + walks + hit_by_pitch + sacrifice_flies
        entry = {
            "date": split.get("date", ""),
            "opponent": split_opponent_code(split),
            "plateAppearances": plate_appearances,
            "atBats": at_bats,
            "hits": hits,
            "homeRuns": safe_stat_int(stat, ["homeRuns", "home_runs"]),
            "walks": walks,
            "strikeouts": safe_stat_int(stat, ["strikeOuts", "strike_outs", "strikeouts"]),
            "totalBases": safe_stat_int(stat, ["totalBases", "total_bases"],) or hits,
        }
        if valid_batter_game_log_sample({**entry, "games": 1}):
            entries.append(entry)
    return sorted(entries, key=lambda item: parse_game_date(item.get("date")), reverse=True)


def summarize_batter_game_log_record(entries: list[dict[str, Any]]) -> dict[str, Any]:
    at_bats = sum(to_int(entry.get("atBats")) for entry in entries)
    hits = sum(to_int(entry.get("hits")) for entry in entries)
    total_bases = sum(to_int(entry.get("totalBases"), to_int(entry.get("hits"))) for entry in entries)
    return {
        "games": len(entries),
        "plateAppearances": sum(to_int(entry.get("plateAppearances")) for entry in entries),
        "atBats": at_bats,
        "hits": hits,
        "homeRuns": sum(to_int(entry.get("homeRuns")) for entry in entries),
        "walks": sum(to_int(entry.get("walks")) for entry in entries),
        "strikeouts": sum(to_int(entry.get("strikeouts")) for entry in entries),
        "totalBases": total_bases,
        "battingAverage": round(hits / at_bats, 3) if at_bats else 0.0,
        "slugging": round(total_bases / at_bats, 3) if at_bats else 0.0,
    }


def pitching_game_log_records_from_splits(
    splits: list[dict[str, Any]],
    pitcher_name: str,
    local_pitcher_id: str,
    mlb_pitcher_id: int,
    season: int,
) -> list[dict[str, Any]]:
    records = []
    source_id = f"mlb-pitching-gamelog-{mlb_pitcher_id}-{season}"
    for split in splits:
        stat = split.get("stat", {}) if isinstance(split.get("stat"), dict) else {}
        innings = to_baseball_innings(stat.get("inningsPitched"))
        strikeouts = safe_stat_int(stat, ["strikeOuts", "strike_outs", "strikeouts"])
        walks = safe_stat_int(stat, ["baseOnBalls", "base_on_balls", "walks"])
        hits_allowed = safe_stat_int(stat, ["hits"])
        runs_allowed = safe_stat_int(stat, ["runs"])
        earned_runs = safe_stat_int(stat, ["earnedRuns", "earned_runs"])
        record = {
            "sourceId": source_id,
            "source": "MLB StatsAPI gameLog",
            "pitcherId": local_pitcher_id or f"mlb-{mlb_pitcher_id}",
            "mlbId": str(mlb_pitcher_id),
            "pitcher": pitcher_name,
            "season": season,
            "date": split.get("date", ""),
            "opponent": split_opponent_code(split),
            "games": 1,
            "innings": innings,
            "hitsAllowed": hits_allowed,
            "runsAllowed": runs_allowed,
            "earnedRuns": earned_runs,
            "homeRunsAllowed": safe_stat_int(stat, ["homeRuns", "home_runs"]),
            "walks": walks,
            "strikeouts": strikeouts,
            "battersFaced": safe_stat_int(stat, ["battersFaced", "batters_faced"]),
            "era": earned_runs * 9 / innings if innings else 0.0,
            "whip": (walks + hits_allowed) / innings if innings else 0.0,
        }
        if any([innings, strikeouts, walks, hits_allowed, runs_allowed, record["battersFaced"]]):
            records.append(record)
    return records


def csv_list(value: str, default: list[str]) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


def first_split_stats(value: Any, limit: int = 5) -> list[dict[str, Any]]:
    payload = public_model(value)
    splits = payload.get("splits", []) if isinstance(payload, dict) else []
    rows = []
    for split in splits[:limit]:
        stat = split.get("stat", {}) if isinstance(split, dict) else {}
        rows.append(stat if isinstance(stat, dict) else {})
    return rows


def summarize_stats_payload(payload: Any, limit: int = 5) -> dict[str, Any]:
    normalized = public_model(payload)
    summary: dict[str, Any] = {}
    if not isinstance(normalized, dict):
        return summary
    for group, stat_types in normalized.items():
        if not isinstance(stat_types, dict):
            continue
        summary[group] = {}
        for stat_type, stat_payload in stat_types.items():
            summary[group][stat_type] = first_split_stats(stat_payload, limit)
    return summary


def compact_people(people: Any, limit: int) -> dict[str, Any]:
    normalized = public_model(people)
    if not isinstance(normalized, list):
        return {"count": 0, "people": []}
    rows = []
    for person in normalized[:limit]:
        if not isinstance(person, dict):
            continue
        rows.append(
            {
                "id": person.get("id"),
                "fullName": person.get("full_name") or person.get("fullName") or person.get("fullname"),
                "primaryPosition": nested_get(person, ["primary_position", "abbreviation"])
                or nested_get(person, ["primaryPosition", "abbreviation"])
                or nested_get(person, ["primaryposition", "abbreviation"]),
                "currentTeam": nested_get(person, ["current_team", "name"])
                or nested_get(person, ["currentTeam", "name"])
                or nested_get(person, ["currentteam", "name"]),
            }
        )
    return {"count": len(normalized), "people": rows}


def compact_schedule(schedule: Any) -> dict[str, Any]:
    payload = public_model(schedule)
    dates = payload.get("dates", []) if isinstance(payload, dict) else []
    games = []
    for date in dates:
        for game in date.get("games", []) or []:
            games.append(
                {
                    "gamePk": game.get("game_pk") or game.get("gamePk"),
                    "status": nested_get(game, ["status", "detailed_state"]) or nested_get(game, ["status", "detailedState"]),
                    "home": nested_get(game, ["teams", "home", "team", "name"]),
                    "away": nested_get(game, ["teams", "away", "team", "name"]),
                    "gameDate": game.get("game_date") or game.get("gameDate"),
                }
            )
    return {"dates": len(dates), "games": games}


def compact_game(game: Any) -> dict[str, Any]:
    payload = public_model(game)
    weather = nested_get(payload, ["game_data", "weather"], {}) or nested_get(payload, ["gameData", "weather"], {}) or {}
    linescore = nested_get(payload, ["live_data", "linescore"], {}) or nested_get(payload, ["liveData", "linescore"], {}) or {}
    game_data = payload.get("game_data") or payload.get("gameData") or {}
    home_info = nested_get(game_data, ["teams", "home"], {}) or {}
    away_info = nested_get(game_data, ["teams", "away"], {}) or {}
    home_status = nested_get(linescore, ["teams", "home"], {}) or {}
    away_status = nested_get(linescore, ["teams", "away"], {}) or {}
    return {
        "gamePk": nested_get(game_data, ["game", "pk"]) or nested_get(game_data, ["game", "game_pk"]),
        "weather": {
            "condition": weather.get("condition"),
            "temperature": weather.get("temp"),
            "wind": weather.get("wind"),
        },
        "linescore": {
            "inning": linescore.get("current_inning_ordinal") or linescore.get("currentInningOrdinal"),
            "inningHalf": linescore.get("inning_half") or linescore.get("inningHalf"),
            "home": {
                "team": f"{home_info.get('franchise_name', '')} {home_info.get('club_name', '')}".strip()
                or home_info.get("name"),
                "runs": home_status.get("runs"),
                "hits": home_status.get("hits"),
                "errors": home_status.get("errors"),
            },
            "away": {
                "team": f"{away_info.get('franchise_name', '')} {away_info.get('club_name', '')}".strip()
                or away_info.get("name"),
                "runs": away_status.get("runs"),
                "hits": away_status.get("hits"),
                "errors": away_status.get("errors"),
            },
        },
    }


def mlb_team_id(mlb: Any, team_name_or_id: str) -> int:
    text = team_name_or_id.strip()
    if text.isdigit():
        return int(text)
    ids = mlb.get_team_id(text)
    if not ids:
        raise MlbStatsApiError(404, f"No MLB team found for {team_name_or_id}.")
    return int(ids[0])


def mlb_player_id(mlb: Any, player_name_or_id: str) -> int:
    text = player_name_or_id.strip()
    if text.isdigit():
        return int(text)
    ids = mlb.get_people_id(text)
    if not ids:
        raise MlbStatsApiError(404, f"No MLB player found for {player_name_or_id}.")
    return int(ids[0])


def mlb_command_response(command: str, query: dict[str, list[str]]) -> dict[str, Any]:
    mlb = mlb_client()
    get = lambda key, default="": query.get(key, [default])[0].strip()
    season = to_int(get("season", str(current_season())), current_season())
    limit = clamp(to_int(get("limit", "50"), 50), 1, 500)
    try:
        if command == "playerStats":
            player_id = mlb_player_id(mlb, get("player"))
            stats = csv_list(get("stats"), ["season", "career"])
            groups = csv_list(get("groups"), ["hitting", "pitching"])
            payload = mlb.get_player_stats(player_id, stats=stats, groups=groups, season=season)
            return {
                "command": command,
                "playerId": player_id,
                "stats": stats,
                "groups": groups,
                "summary": summarize_stats_payload(payload, int(limit)),
                "raw": public_model(payload),
            }

        if command == "expectedStats":
            player_id = mlb_player_id(mlb, get("player"))
            payload = mlb.get_player_stats(player_id, stats=["expectedStatistics"], groups=["hitting"], season=season)
            return {
                "command": command,
                "playerId": player_id,
                "summary": summarize_stats_payload(payload, int(limit)),
                "raw": public_model(payload),
            }

        if command == "vsPlayerStats":
            batter_id = mlb_player_id(mlb, get("player"))
            opposing_id = mlb_player_id(mlb, get("opposingPlayer"))
            payload = mlb.get_player_stats(
                batter_id,
                stats=["vsPlayer"],
                groups=["hitting"],
                opposingPlayerId=opposing_id,
                season=season,
            )
            return {
                "command": command,
                "playerId": batter_id,
                "opposingPlayerId": opposing_id,
                "summary": summarize_stats_payload(payload, int(limit)),
                "raw": public_model(payload),
            }

        if command == "hotColdZones":
            player_id = mlb_player_id(mlb, get("player"))
            payload = mlb.get_player_stats(player_id, stats=["hotColdZones"], groups=["hitting"], season=season)
            return {
                "command": command,
                "playerId": player_id,
                "summary": summarize_stats_payload(payload, int(limit)),
                "raw": public_model(payload),
            }

        if command == "teamStats":
            team_id = mlb_team_id(mlb, get("team"))
            stats = csv_list(get("stats"), ["season", "seasonAdvanced"])
            groups = csv_list(get("groups"), ["hitting"])
            payload = mlb.get_team_stats(team_id, stats=stats, groups=groups, season=season)
            return {
                "command": command,
                "teamId": team_id,
                "stats": stats,
                "groups": groups,
                "summary": summarize_stats_payload(payload, int(limit)),
                "raw": public_model(payload),
            }

        if command == "schedule":
            date = get("date")
            if not date:
                raise MlbStatsApiError(400, "Enter a schedule date.")
            payload = mlb.get_schedule(date=date)
            return {"command": command, "summary": compact_schedule(payload), "raw": public_model(payload)}

        if command == "game":
            game_id = to_int(get("gameId"))
            payload = mlb.get_game(game_id)
            return {"command": command, "gameId": game_id, "summary": compact_game(payload), "raw": public_model(payload)}

        if command == "playByPlay":
            game_id = to_int(get("gameId"))
            payload = mlb.get_game_play_by_play(game_id)
            return {"command": command, "gameId": game_id, "raw": public_model(payload)}

        if command == "lineScore":
            game_id = to_int(get("gameId"))
            payload = mlb.get_game_line_score(game_id)
            return {"command": command, "gameId": game_id, "raw": public_model(payload)}

        if command == "boxScore":
            game_id = to_int(get("gameId"))
            payload = mlb.get_game_box_score(game_id)
            return {"command": command, "gameId": game_id, "raw": public_model(payload)}

        if command == "gamepace":
            payload = mlb.get_gamepace(season=season)
            return {"command": command, "season": season, "raw": public_model(payload)}

        if command == "people":
            payload = mlb.get_people(sport_id=to_int(get("sportId", "1"), 1))
            return {"command": command, **compact_people(payload, int(limit))}

        if command == "peopleId":
            ids = mlb.get_people_id(get("player"))
            return {"command": command, "ids": ids}

        if command == "team":
            team_id = mlb_team_id(mlb, get("team"))
            payload = mlb.get_team(team_id)
            return {"command": command, "teamId": team_id, "raw": public_model(payload)}

        if command == "teamRoster":
            team_id = mlb_team_id(mlb, get("team"))
            payload = mlb.get_team_roster(team_id)
            return {"command": command, "teamId": team_id, "raw": public_model(payload)}

        if command == "teamCoaches":
            team_id = mlb_team_id(mlb, get("team"))
            payload = mlb.get_team_coaches(team_id)
            return {"command": command, "teamId": team_id, "raw": public_model(payload)}

        if command == "draft":
            year = get("season", str(current_season()))
            payload = mlb.get_draft(year)
            return {"command": command, "year": year, "raw": public_model(payload)}

        if command == "awards":
            award_id = get("awardId")
            if not award_id:
                raise MlbStatsApiError(400, "Enter an award id.")
            payload = mlb.get_awards(award_id=award_id)
            return {"command": command, "awardId": award_id, "raw": public_model(payload)}

        if command == "venue":
            venue = get("venue")
            if venue.isdigit():
                venue_id = int(venue)
            else:
                ids = mlb.get_venue_id(venue)
                if not ids:
                    raise MlbStatsApiError(404, f"No venue found for {venue}.")
                venue_id = int(ids[0])
            payload = mlb.get_venue(venue_id)
            return {"command": command, "venueId": venue_id, "raw": public_model(payload)}

        if command == "division":
            division_id = to_int(get("divisionId"))
            payload = mlb.get_division(division_id)
            return {"command": command, "divisionId": division_id, "raw": public_model(payload)}

        if command == "league":
            league_id = to_int(get("leagueId"))
            payload = mlb.get_league(league_id)
            return {"command": command, "leagueId": league_id, "raw": public_model(payload)}

        if command == "season":
            payload = mlb.get_season(season)
            return {"command": command, "season": season, "raw": public_model(payload)}

        if command == "standings":
            league_id = to_int(get("leagueId", "103"), 103)
            payload = mlb.get_standings(league_id, season)
            return {"command": command, "leagueId": league_id, "season": season, "raw": public_model(payload)}

    except MlbStatsApiError:
        raise
    except Exception as error:
        raise MlbStatsApiError(502, f"MLB StatsAPI command failed: {error}") from error

    raise MlbStatsApiError(400, f"Unsupported MLB StatsAPI command: {command}")


def mlb_package_status() -> dict[str, Any]:
    try:
        import mlbstatsapi  # type: ignore
    except ImportError:
        return {
            "installed": False,
            "package": "python-mlb-statsapi",
            "importName": "mlbstatsapi",
            "installCommand": "python -m pip install -r requirements.txt",
            "repository": "https://github.com/zero-sum-seattle/python-mlb-statsapi",
        }
    return {
        "installed": True,
        "package": "python-mlb-statsapi",
        "importName": "mlbstatsapi",
        "version": getattr(mlbstatsapi, "__version__", "installed"),
        "repository": "https://github.com/zero-sum-seattle/python-mlb-statsapi",
    }


def mlb_player_lookup(name: str, season: int, store: bool = True) -> dict[str, Any]:
    if not name.strip():
        raise MlbStatsApiError(400, "Enter a player name.")
    mlb = mlb_client()
    season = season or current_season()
    try:
        people_ids = mlb.get_people_id(name.strip())
    except Exception as error:
        raise MlbStatsApiError(502, f"MLB StatsAPI lookup failed: {error}") from error
    if not people_ids:
        raise MlbStatsApiError(404, f"No MLB player found for {name}.")

    player_id = people_ids[0]
    try:
        person = public_model(mlb.get_person(player_id))
    except Exception:
        person = {}
    try:
        stats_payload = mlb.get_player_stats(
            player_id,
            stats=["season"],
            groups=["hitting", "pitching"],
            season=season,
        )
    except Exception as error:
        raise MlbStatsApiError(502, f"Could not load player stats: {error}") from error

    hitting = stat_from_splits(stats_payload, "hitting", "season")
    pitching = stat_from_splits(stats_payload, "pitching", "season")
    at_bats = safe_stat_int(hitting, ["atBats", "at_bats"])
    hits = safe_stat_int(hitting, ["hits"])
    batting_average = safe_stat_number(hitting, ["avg", "battingAverage", "batting_average"]) or (hits / at_bats if at_bats else 0.0)
    payload = {
        "source": "python-mlb-statsapi",
        "season": season,
        "player": {
            "id": player_id,
            "name": person.get("fullname") or person.get("fullName") or person.get("full_name") or name.strip(),
            "primaryPosition": nested_get(person, ["primaryposition", "abbreviation"])
            or nested_get(person, ["primaryPosition", "abbreviation"])
            or nested_get(person, ["primary_position", "abbreviation"]),
            "currentTeam": nested_get(person, ["currentteam", "name"])
            or nested_get(person, ["currentTeam", "name"])
            or nested_get(person, ["current_team", "name"]),
            "batSide": person_hand_code(person, "batSide"),
            "pitchHand": person_hand_code(person, "pitchHand"),
        },
        "batting": {
            "games": safe_stat_int(hitting, ["gamesPlayed", "games_played"]),
            "plateAppearances": safe_stat_int(hitting, ["plateAppearances", "plate_appearances"]),
            "atBats": at_bats,
            "hits": hits,
            "doubles": safe_stat_int(hitting, ["doubles"]),
            "triples": safe_stat_int(hitting, ["triples"]),
            "homeRuns": safe_stat_int(hitting, ["homeRuns", "home_runs"]),
            "walks": safe_stat_int(hitting, ["baseOnBalls", "base_on_balls", "walks"]),
            "strikeouts": safe_stat_int(hitting, ["strikeOuts", "strike_outs", "strikeouts"]),
            "battingAverage": batting_average,
            "onBase": safe_stat_number(hitting, ["obp", "onBase", "on_base"]),
            "slugging": safe_stat_number(hitting, ["slg", "slugging"]),
            "ops": safe_stat_number(hitting, ["ops"]),
            "totalBases": safe_stat_int(hitting, ["totalBases", "total_bases"]),
        },
        "pitching": {
            "games": safe_stat_int(pitching, ["gamesPlayed", "games_played"]),
            "gamesStarted": safe_stat_int(pitching, ["gamesStarted", "games_started"]),
            "innings": safe_stat_number(pitching, ["inningsPitched", "innings_pitched"]),
            "hitsAllowed": safe_stat_int(pitching, ["hits", "hitsAllowed", "hits_allowed"]),
            "runsAllowed": safe_stat_int(pitching, ["runs", "runsAllowed", "runs_allowed"]),
            "earnedRuns": safe_stat_int(pitching, ["earnedRuns", "earned_runs"]),
            "homeRunsAllowed": safe_stat_int(pitching, ["homeRuns", "home_runs", "homeRunsAllowed", "home_runs_allowed"]),
            "strikeouts": safe_stat_int(pitching, ["strikeOuts", "strike_outs", "strikeouts"]),
            "walks": safe_stat_int(pitching, ["baseOnBalls", "base_on_balls", "walks"]),
            "battersFaced": safe_stat_int(pitching, ["battersFaced", "batters_faced"]),
            "era": safe_stat_number(pitching, ["era"]),
            "fip": safe_stat_number(pitching, ["fip"]),
            "whip": safe_stat_number(pitching, ["whip"]),
            "hitsPerNine": safe_stat_number(pitching, ["hitsPer9Inn", "hits_per9_inn", "hitsPerNine"]),
        },
    }
    if store:
        batting_store = upsert_player_from_mlb_payload(payload)
        pitching_store = upsert_pitcher_from_mlb_payload(payload)
        payload["stored"] = {
            **batting_store,
            "batting": batting_store,
            "pitching": pitching_store,
        }
        if batting_store.get("action") == "skipped" and pitching_store.get("action") != "skipped":
            payload["stored"].update(pitching_store)
    else:
        payload["stored"] = {"action": "skipped"}
    return payload


def source_capability_map() -> dict[str, Any]:
    meta = load_dataset_meta()
    capabilities = [
        {
            "need": "Batter game logs by opponent",
            "sources": ["MLB StatsAPI boxscores/play-by-play", "Baseball-Reference player logs"],
            "status": "loaded" if meta.get("gameLogs", {}).get("loaded") else "refreshable",
            "file": str(GAME_LOG_FILE.name),
            "notes": "Model refresh pulls selected batter game logs from MLB StatsAPI; Baseball-Reference can still be used for manual backfill.",
        },
        {
            "need": "Pitching game logs by opponent",
            "sources": ["MLB StatsAPI boxscores/play-by-play", "Baseball-Reference pitching logs"],
            "status": "loaded" if meta.get("pitchingGameLogs", {}).get("loaded") else "refreshable",
            "file": str(PITCHING_GAME_LOG_FILE.name),
            "notes": "Model refresh pulls selected pitcher game logs from MLB StatsAPI for workload, Ks, walks, runs, hits, HR allowed, and opponent history.",
        },
        {
            "need": "Advanced batter-vs-pitcher matchups",
            "sources": ["MLB StatsAPI vsPlayer", "Baseball Savant Statcast Search CSV"],
            "status": "refreshable" if meta.get("batting", {}).get("loaded") and meta.get("pitching", {}).get("loaded") else "needs-player-pitcher",
            "file": str(BATTER_PITCHER_ADVANCED_FILE.name),
            "notes": "MLB StatsAPI supplies outcome history; Baseball Savant supplies pitch/contact quality such as xwOBA, barrels, whiffs, EV, and LA.",
        },
        {
            "need": "Handedness splits",
            "sources": ["Baseball Savant Statcast Search CSV", "MLB StatsAPI splits where available"],
            "status": "refreshable",
            "file": str(HANDEDNESS_SPLITS_FILE.name),
            "notes": "Batter rows split by pitcher hand; pitcher rows split by batter side.",
        },
        {
            "need": "Rolling 7/14/30-day form",
            "sources": ["Baseball Savant Statcast Search CSV", "MLB StatsAPI game feeds"],
            "status": "refreshable",
            "file": str(ROLLING_FORM_FILE.name),
            "notes": "Uses pitch-level Statcast rows to derive PA, H, HR, SO, barrel, hard-hit, and K%.",
        },
        {
            "need": "Confirmed starters, lineups, park, weather",
            "sources": ["MLB StatsAPI schedule/game/boxscore", "ESPN scoreboard", "BallparkPal API/export"],
            "status": "refreshable",
            "file": str(GAME_CONTEXT_FILE.name),
            "notes": "ESPN is fast for probables; MLB game feeds are better for venue/weather and lineups after they are posted.",
        },
        {
            "need": "Weather-adjusted park environment",
            "sources": ["BallparkPal API/export", "Manual weather CSV"],
            "status": "loaded" if meta.get("ballparkContext", {}).get("loaded") else "refreshable",
            "file": str(BALLPARK_CONTEXT_FILE.name),
            "notes": "Stores venue, roof, wind, temperature, park factor, hit factor, and HR factor for model adjustments.",
        },
        {
            "need": "Pitch arsenal and pitch-type performance",
            "sources": ["Baseball Savant Statcast Search CSV"],
            "status": "refreshable",
            "file": str(PITCH_ARSENAL_FILE.name),
            "notes": "Pitch type usage, whiff rate, velocity, and batted-ball damage by pitch type.",
        },
        {
            "need": "Statcast quality metrics",
            "sources": ["Baseball Savant Statcast Search CSV"],
            "status": "refreshable",
            "file": str(STATCAST_QUALITY_FILE.name),
            "notes": "xBA, xSLG, xwOBA, barrel%, hard-hit%, launch angle, and exit velocity.",
        },
    ]
    return {"capabilities": capabilities, "datasets": meta}


def statcast_date_range(season: int, lookback_days: int = 45) -> tuple[str, str]:
    today = datetime.now().date()
    season_start = datetime(season, 3, 1).date()
    if today.year != season:
        return f"{season}-03-01", f"{season}-11-30"
    start = max(today - timedelta(days=lookback_days), season_start)
    return start.isoformat(), today.isoformat()


def statcast_search_rows(
    player_type: str,
    player_id: int,
    start_date: str,
    end_date: str,
) -> list[dict[str, str]]:
    params = {
        "all": "true",
        "hfPT": "",
        "hfAB": "",
        "hfGT": "R|",
        "hfPR": "",
        "hfZ": "",
        "stadium": "",
        "hfBBL": "",
        "hfNewZones": "",
        "hfPull": "",
        "hfC": "",
        "hfSea": "",
        "hfSit": "",
        "player_type": player_type,
        "hfOuts": "",
        "opponent": "",
        "pitcher_throws": "",
        "batter_stands": "",
        "hfSA": "",
        "game_date_gt": start_date,
        "game_date_lt": end_date,
        "team": "",
        "position": "",
        "hfRO": "",
        "home_road": "",
        "hfFlag": "",
        "hfBBT": "",
        "metric_1": "",
        "hfInn": "",
        "min_pitches": "0",
        "min_results": "0",
        "group_by": "name",
        "sort_col": "pitches",
        "player_event_sort": "h_launch_speed",
        "sort_order": "desc",
        "min_pas": "0",
        "min_abs": "0",
        "type": "details",
    }
    lookup_key = "batters_lookup[]" if player_type == "batter" else "pitchers_lookup[]"
    params[lookup_key] = str(player_id)
    url = f"{BASEBALL_SAVANT_SEARCH_CSV}?{urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor", "Accept": "text/csv,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(25_000_000).decode("utf-8-sig", errors="replace")
    except TimeoutError as error:
        raise ValueError("Baseball Savant timed out while preparing Statcast CSV data.") from error
    except urllib.error.URLError as error:
        raise ValueError(f"Could not reach Baseball Savant: {error.reason}") from error
    return normalize_rows(raw)


HIT_EVENTS = {"single", "double", "triple", "home_run"}
WALK_EVENTS = {"walk", "intent_walk"}
STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
NON_AB_EVENTS = WALK_EVENTS | {"hit_by_pitch", "sac_bunt", "sac_fly", "catcher_interf"}
SWING_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "hit_into_play",
    "hit_into_play_no_out",
    "hit_into_play_score",
    "foul_bunt",
    "missed_bunt",
}
WHIFF_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}


def statcast_event_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if first_value(row, ["events"])]


def average_nonzero(values: list[float]) -> float:
    filtered = [value for value in values if value]
    return sum(filtered) / len(filtered) if filtered else 0.0


def summarize_statcast_rows(rows: list[dict[str, str]], label: str = "") -> dict[str, Any]:
    events = statcast_event_rows(rows)
    at_bats = sum(1 for row in events if first_value(row, ["events"]) not in NON_AB_EVENTS)
    hits = sum(1 for row in events if first_value(row, ["events"]) in HIT_EVENTS)
    home_runs = sum(1 for row in events if first_value(row, ["events"]) == "home_run")
    walks = sum(1 for row in events if first_value(row, ["events"]) in WALK_EVENTS)
    strikeouts = sum(1 for row in events if first_value(row, ["events"]) in STRIKEOUT_EVENTS)
    swings = sum(1 for row in rows if first_value(row, ["description"]) in SWING_DESCRIPTIONS)
    whiffs = sum(1 for row in rows if first_value(row, ["description"]) in WHIFF_DESCRIPTIONS)
    batted = [row for row in rows if to_float(first_value(row, ["launch_speed"]))]
    barrels = sum(1 for row in batted if to_int(first_value(row, ["launch_speed_angle"])) == 6)
    hard_hits = sum(1 for row in batted if to_float(first_value(row, ["launch_speed"])) >= 95)
    woba_denom = sum(to_float(first_value(row, ["woba_denom"])) for row in events)
    woba_value = sum(to_float(first_value(row, ["woba_value"])) for row in events)
    return {
        "label": label,
        "pitches": len(rows),
        "plateAppearances": len(events),
        "atBats": at_bats,
        "hits": hits,
        "homeRuns": home_runs,
        "walks": walks,
        "strikeouts": strikeouts,
        "battingAverage": round(hits / at_bats, 3) if at_bats else 0.0,
        "strikeoutRate": round(strikeouts / len(events), 3) if events else 0.0,
        "walkRate": round(walks / len(events), 3) if events else 0.0,
        "woba": round(woba_value / woba_denom, 3) if woba_denom else 0.0,
        "xwoba": round(average_nonzero([to_float(first_value(row, ["estimated_woba_using_speedangle"])) for row in events]), 3),
        "xba": round(average_nonzero([to_float(first_value(row, ["estimated_ba_using_speedangle"])) for row in events]), 3),
        "xslg": round(average_nonzero([to_float(first_value(row, ["estimated_slg_using_speedangle"])) for row in events]), 3),
        "exitVelocity": round(average_nonzero([to_float(first_value(row, ["launch_speed"])) for row in batted]), 1),
        "launchAngle": round(average_nonzero([to_float(first_value(row, ["launch_angle"])) for row in batted]), 1),
        "barrels": barrels,
        "barrelRate": round(barrels / len(batted), 3) if batted else 0.0,
        "hardHitRate": round(hard_hits / len(batted), 3) if batted else 0.0,
        "whiffs": whiffs,
        "swings": swings,
        "whiffRate": round(whiffs / swings, 3) if swings else 0.0,
        "battedBalls": len(batted),
    }


def rows_since(rows: list[dict[str, str]], days: int) -> list[dict[str, str]]:
    cutoff = datetime.now() - timedelta(days=days)
    selected = []
    for row in rows:
        date = parse_game_date(first_value(row, ["game_date"]))
        if date != datetime.min and date >= cutoff:
            selected.append(row)
    return selected


def statcast_handedness_splits(rows: list[dict[str, str]], role: str, player_name: str, player_id: int, season: int) -> list[dict[str, Any]]:
    field = "p_throws" if role == "batter" else "stand"
    label_prefix = "vs pitcher throws" if role == "batter" else "vs batter stands"
    splits = []
    for hand in ["L", "R"]:
        subset = [row for row in rows if first_value(row, [field]).upper() == hand]
        if subset:
            splits.append(
                {
                    "playerId": str(player_id),
                    "player": player_name,
                    "role": role,
                    "season": season,
                    "split": hand,
                    "label": f"{label_prefix} {hand}",
                    **summarize_statcast_rows(subset, f"{role} {hand}"),
                }
            )
    return splits


def statcast_rolling_form(rows: list[dict[str, str]], role: str, player_name: str, player_id: int, season: int) -> list[dict[str, Any]]:
    return [
        {
            "playerId": str(player_id),
            "player": player_name,
            "role": role,
            "season": season,
            "windowDays": days,
            **summarize_statcast_rows(rows_since(rows, days), f"Last {days} days"),
        }
        for days in [7, 14, 30]
    ]


def statcast_pitch_arsenal(rows: list[dict[str, str]], pitcher_name: str, pitcher_id: int, season: int) -> list[dict[str, Any]]:
    by_pitch: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        pitch_type = first_value(row, ["pitch_type", "pitch_name"]) or "UNK"
        by_pitch.setdefault(pitch_type, []).append(row)
    total_pitches = len(rows) or 1
    arsenal = []
    for pitch_type, pitch_rows in sorted(by_pitch.items(), key=lambda item: len(item[1]), reverse=True):
        summary = summarize_statcast_rows(pitch_rows, pitch_type)
        summary.update(
            {
                "pitcherId": str(pitcher_id),
                "pitcher": pitcher_name,
                "season": season,
                "pitchType": pitch_type,
                "usageRate": round(len(pitch_rows) / total_pitches, 3),
                "velocity": round(average_nonzero([to_float(first_value(row, ["release_speed"])) for row in pitch_rows]), 1),
            }
        )
        arsenal.append(summary)
    return arsenal[:12]


def upsert_records_by_key(path: Path, records: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    existing = load_json_file(path, [])
    merged = {record_key(record, key_fields): record for record in existing if record_key(record, key_fields).strip("|")}
    for record in records:
        key = record_key(record, key_fields)
        if key.strip("|"):
            merged[key] = {**merged.get(key, {}), **record}
    output = list(merged.values())
    save_json_file(path, output)
    return output


def remove_json_records(path: Path, predicate: Any) -> int:
    records = load_json_file(path, [])
    if not records:
        return 0
    kept = [record for record in records if not predicate(record)]
    removed = len(records) - len(kept)
    if removed:
        save_json_file(path, kept)
    return removed


def selected_player_by_id(player_id: str) -> Player | None:
    return next((player for player in load_players() if player.player_id == player_id), None)


def mlb_id_for_name(name: str) -> int:
    return mlb_player_id(mlb_client(), name)


def refresh_batter_game_logs_from_mlb(name: str, season: int, local_player_id: str = "") -> dict[str, Any]:
    player_id = mlb_id_for_name(name)
    entries = batter_game_log_entries_from_splits(mlb_game_log_splits(player_id, "hitting", season))
    if not entries:
        return {"status": "empty", "player": name, "playerId": player_id, "count": 0}
    record = {
        "sourceId": f"mlb-batter-gamelog-{player_id}-{season}",
        "source": "MLB StatsAPI gameLog",
        "playerId": local_player_id or f"mlb-{player_id}",
        "mlbId": str(player_id),
        "player": name,
        "season": season,
        "opponent": "",
        "entries": entries,
        **summarize_batter_game_log_record(entries),
    }
    records = upsert_records_by_key(GAME_LOG_FILE, [record], ["sourceId", "playerId", "player", "season"])
    update_dataset_meta("gameLogs", "MLB StatsAPI gameLog", len(records))
    return {
        "status": "loaded",
        "player": name,
        "playerId": player_id,
        "count": len(entries),
        "storedCount": len(records),
    }


def refresh_pitching_game_logs_from_mlb(name: str, season: int, local_pitcher_id: str = "") -> dict[str, Any]:
    pitcher_id = mlb_id_for_name(name)
    records_to_add = pitching_game_log_records_from_splits(
        mlb_game_log_splits(pitcher_id, "pitching", season),
        name,
        local_pitcher_id,
        pitcher_id,
        season,
    )
    if not records_to_add:
        return {"status": "empty", "pitcher": name, "pitcherId": pitcher_id, "count": 0}
    records = upsert_records_by_key(
        PITCHING_GAME_LOG_FILE,
        records_to_add,
        ["sourceId", "pitcherId", "pitcher", "date", "opponent"],
    )
    update_dataset_meta("pitchingGameLogs", "MLB StatsAPI gameLog", len(records))
    return {
        "status": "loaded",
        "pitcher": name,
        "pitcherId": pitcher_id,
        "count": len(records_to_add),
        "storedCount": len(records),
    }


def matchup_from_mlb_vs_player(batter_name: str, pitcher_name: str, season: int) -> dict[str, Any]:
    mlb = mlb_client()
    batter_id = mlb_player_id(mlb, batter_name)
    pitcher_id = mlb_player_id(mlb, pitcher_name)
    payload = mlb.get_player_stats(
        batter_id,
        stats=["vsPlayer"],
        groups=["hitting"],
        opposingPlayerId=pitcher_id,
        season=season,
    )
    stats = stat_from_splits(payload, "hitting", "vsPlayer")
    at_bats = safe_stat_int(stats, ["atBats", "at_bats"])
    hits = safe_stat_int(stats, ["hits"])
    plate_appearances = safe_stat_int(stats, ["plateAppearances", "plate_appearances"]) or at_bats + safe_stat_int(stats, ["baseOnBalls", "base_on_balls", "walks"])
    return {
        "batter": batter_name,
        "batterId": f"mlb-{batter_id}",
        "pitcher": pitcher_name,
        "pitcherId": f"mlb-{pitcher_id}",
        "season": season,
        "plateAppearances": plate_appearances,
        "atBats": at_bats,
        "hits": hits,
        "homeRuns": safe_stat_int(stats, ["homeRuns", "home_runs"]),
        "walks": safe_stat_int(stats, ["baseOnBalls", "base_on_balls", "walks"]),
        "strikeouts": safe_stat_int(stats, ["strikeOuts", "strike_outs", "strikeouts"]),
        "battingAverage": safe_stat_number(stats, ["avg", "battingAverage", "batting_average"]) or (hits / at_bats if at_bats else 0.0),
        "onBase": safe_stat_number(stats, ["obp", "onBase", "on_base"]),
        "slugging": safe_stat_number(stats, ["slg", "slugging"]),
        "ops": safe_stat_number(stats, ["ops"]),
        "sources": ["MLB StatsAPI vsPlayer"],
    }


def enrich_matchup_with_statcast(record: dict[str, Any], season: int) -> tuple[dict[str, Any], dict[str, Any]]:
    batter_id = int(str(record.get("batterId", "")).removeprefix("mlb-") or 0)
    pitcher_id = int(str(record.get("pitcherId", "")).removeprefix("mlb-") or 0)
    if not batter_id or not pitcher_id:
        return record, {"status": "skipped", "reason": "Missing MLB ids for Statcast matchup."}
    start, end = statcast_date_range(season, 220)
    rows = statcast_search_rows("batter", batter_id, start, end)
    matchup_rows = [row for row in rows if to_int(first_value(row, ["pitcher"])) == pitcher_id]
    if not matchup_rows:
        return record, {"status": "empty", "rows": 0}
    summary = summarize_statcast_rows(matchup_rows, "Batter vs pitcher Statcast")
    record.update(
        {
            "plateAppearances": summary["plateAppearances"] or record.get("plateAppearances", 0),
            "atBats": summary["atBats"] or record.get("atBats", 0),
            "hits": summary["hits"] or record.get("hits", 0),
            "homeRuns": summary["homeRuns"] or record.get("homeRuns", 0),
            "walks": summary["walks"] or record.get("walks", 0),
            "strikeouts": summary["strikeouts"] or record.get("strikeouts", 0),
            "battingAverage": summary["battingAverage"] or record.get("battingAverage", 0.0),
            "woba": summary["woba"],
            "xwoba": summary["xwoba"],
            "xba": summary["xba"],
            "xslg": summary["xslg"],
            "exitVelocity": summary["exitVelocity"],
            "launchAngle": summary["launchAngle"],
            "hardHitRate": summary["hardHitRate"],
            "barrelRate": summary["barrelRate"],
            "whiffRate": summary["whiffRate"],
            "sources": list(dict.fromkeys([*record.get("sources", []), "Baseball Savant Statcast Search"])),
        }
    )
    return record, {"status": "loaded", "rows": len(matchup_rows), "pitches": summary["pitches"]}


def refresh_statcast_context_for_player(name: str, role: str, season: int, player_id: int | None = None) -> dict[str, Any]:
    resolved_id = player_id or mlb_id_for_name(name)
    start, end = statcast_date_range(season, 220)
    rows = statcast_search_rows(role, resolved_id, start, end)
    quality = {
        "playerId": str(resolved_id),
        "player": name,
        "role": role,
        "season": season,
        "startDate": start,
        "endDate": end,
        **summarize_statcast_rows(rows, f"{name} Statcast"),
    }
    quality_rows = upsert_records_by_key(STATCAST_QUALITY_FILE, [quality], ["playerId", "role", "season"])
    split_rows = upsert_records_by_key(
        HANDEDNESS_SPLITS_FILE,
        statcast_handedness_splits(rows, role, name, resolved_id, season),
        ["playerId", "role", "season", "split"],
    )
    rolling_rows = upsert_records_by_key(
        ROLLING_FORM_FILE,
        statcast_rolling_form(rows, role, name, resolved_id, season),
        ["playerId", "role", "season", "windowDays"],
    )
    arsenal_count = 0
    if role == "pitcher":
        arsenal_rows = upsert_records_by_key(
            PITCH_ARSENAL_FILE,
            statcast_pitch_arsenal(rows, name, resolved_id, season),
            ["pitcherId", "season", "pitchType"],
        )
        arsenal_count = len(arsenal_rows)
    update_dataset_meta("statcastQuality", "Baseball Savant Statcast Search", len(quality_rows))
    update_dataset_meta("handednessSplits", "Baseball Savant Statcast Search", len(split_rows))
    update_dataset_meta("rollingForm", "Baseball Savant Statcast Search", len(rolling_rows))
    if role == "pitcher":
        update_dataset_meta("pitchArsenal", "Baseball Savant Statcast Search", arsenal_count)
    return {
        "status": "loaded",
        "player": name,
        "role": role,
        "playerId": resolved_id,
        "statcastRows": len(rows),
        "quality": quality,
    }


def refresh_batter_pitcher_matchup_data(batter_name: str, pitcher_name: str, season: int) -> dict[str, Any]:
    record = matchup_from_mlb_vs_player(batter_name, pitcher_name, season)
    statcast_status: dict[str, Any]
    try:
        record, statcast_status = enrich_matchup_with_statcast(record, season)
    except ValueError as error:
        statcast_status = {"status": "error", "error": str(error)}
    records = upsert_records_by_key(BATTER_PITCHER_ADVANCED_FILE, [record], ["batterId", "batter", "pitcherId", "pitcher", "season"])
    update_dataset_meta("batterPitcherAdvanced", "MLB StatsAPI vsPlayer + Baseball Savant", len(records))
    return {
        "status": "loaded",
        "record": record,
        "statcast": statcast_status,
        "count": len(records),
    }


def ballparkpal_headers() -> dict[str, str]:
    headers = {"Accept": "application/json,text/csv,*/*", "User-Agent": "baseball-prop-predictor"}
    token = os.environ.get("BALLPARKPAL_API_KEY") or os.environ.get("BALLPARKPAL_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-API-Key"] = token
    return headers


def ballparkpal_url(date: str, team_code: str = "") -> str:
    template = os.environ.get("BALLPARKPAL_API_URL", "").strip()
    if template:
        return template.format(date=date, team=team_code, opponent=team_code)
    base = os.environ.get("BALLPARKPAL_API_BASE", BALLPARKPAL_API_BASE).rstrip("/")
    query = urlencode({key: value for key, value in {"date": date, "team": team_code}.items() if value})
    return f"{base}/park-factors?{query}" if query else f"{base}/park-factors"


def extract_ballparkpal_items(payload: Any) -> list[dict[str, Any]]:
    payload = public_model(payload)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["games", "data", "events", "parkFactors", "parks", "results"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def normalize_ballparkpal_item(item: dict[str, Any], date: str = "") -> dict[str, Any]:
    home = normalize_team_code(str(item.get("homeTeam") or item.get("home_team") or item.get("home") or nested_get(item, ["home", "abbr"], "") or nested_get(item, ["home", "team"], "")))
    away = normalize_team_code(str(item.get("awayTeam") or item.get("away_team") or item.get("away") or item.get("roadTeam") or nested_get(item, ["away", "abbr"], "") or nested_get(item, ["away", "team"], "")))
    venue = str(item.get("venue") or item.get("ballpark") or item.get("park") or item.get("stadium") or item.get("venueName") or "").strip()
    weather = item.get("weather") if isinstance(item.get("weather"), dict) else {}
    wind = item.get("wind") if isinstance(item.get("wind"), dict) else {}
    return {
        "source": "BallparkPal API",
        "date": str(item.get("date") or item.get("gameDate") or date or ""),
        "gameId": str(item.get("gameId") or item.get("gamePk") or item.get("eventId") or item.get("id") or ""),
        "game": str(item.get("game") or item.get("matchup") or f"{away or '--'} @ {home or '--'}"),
        "venue": venue,
        "city": str(item.get("city") or ""),
        "homeTeam": home,
        "awayTeam": away,
        "temperature": to_float(item.get("temperature") or item.get("temp") or weather.get("temperature") or weather.get("temp")),
        "windMph": to_float(item.get("windMph") or item.get("windSpeed") or wind.get("mph") or wind.get("speed")),
        "windDirection": str(item.get("windDirection") or item.get("windDir") or wind.get("direction") or "").lower(),
        "roof": str(item.get("roof") or item.get("roofStatus") or item.get("dome") or "").lower(),
        "weather": str(item.get("condition") or item.get("weatherCondition") or weather.get("condition") or ""),
        "parkFactor": round(normalize_factor(item.get("parkFactor") or item.get("runFactor") or item.get("runsFactor")), 3),
        "homeRunFactor": round(normalize_factor(item.get("hrFactor") or item.get("homeRunFactor") or item.get("homeRunsFactor"), normalize_factor(item.get("parkFactor") or item.get("runFactor"))), 3),
        "hitFactor": round(normalize_factor(item.get("hitFactor") or item.get("hitsFactor") or item.get("singleFactor"), normalize_factor(item.get("parkFactor") or item.get("runFactor"))), 3),
        "runFactor": round(normalize_factor(item.get("runFactor") or item.get("runsFactor") or item.get("parkFactor")), 3),
        "raw": item,
    }


def fetch_ballparkpal_context(date: str, team_code: str = "") -> dict[str, Any]:
    if not (os.environ.get("BALLPARKPAL_API_KEY") or os.environ.get("BALLPARKPAL_TOKEN") or os.environ.get("BALLPARKPAL_API_URL")):
        return {"status": "skipped", "count": 0, "reason": "Set BALLPARKPAL_API_KEY or BALLPARKPAL_API_URL to pull BallparkPal data."}
    url = ballparkpal_url(date, team_code)
    request = urllib.request.Request(url, headers=ballparkpal_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(8_000_000).decode("utf-8-sig", errors="replace")
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return {"status": "error", "count": 0, "endpoint": url, "error": raw or str(error)}
    except urllib.error.URLError as error:
        return {"status": "error", "count": 0, "endpoint": url, "error": f"Could not reach BallparkPal: {error.reason}"}

    if "csv" in content_type.lower() or raw.lstrip().startswith(("Home Team", "Date,")):
        contexts = parse_ballpark_context(raw)
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            return {"status": "error", "count": 0, "endpoint": url, "error": f"BallparkPal response was not JSON or CSV: {error}"}
        contexts = [normalize_ballparkpal_item(item, date) for item in extract_ballparkpal_items(payload)]
        contexts = [context for context in contexts if any([context.get("homeTeam"), context.get("awayTeam"), context.get("venue")])]
    if team_code:
        normalized_team = normalize_team_code(team_code)
        contexts = [
            context
            for context in contexts
            if normalized_team in {normalize_team_code(str(context.get("homeTeam", ""))), normalize_team_code(str(context.get("awayTeam", "")))}
        ]
    stored = upsert_records_by_key(BALLPARK_CONTEXT_FILE, contexts, ["gameId", "date", "homeTeam", "awayTeam", "venue"])
    update_dataset_meta("ballparkContext", "BallparkPal API", len(stored))
    return {"status": "loaded", "count": len(contexts), "storedCount": len(stored), "endpoint": url, "contexts": contexts[:8]}


def refresh_game_context(date: str, team_code: str = "") -> dict[str, Any]:
    contexts: list[dict[str, Any]] = []
    params = {"dates": date.replace("-", "") if date else ""}
    try:
        scoreboard = espn_scoreboard(params)
        for event in scoreboard.get("events", []):
            teams = [event.get("home", {}), event.get("away", {})]
            codes = {
                normalize_team_code(str((item.get("team") or {}).get("abbreviation") or (item.get("team") or {}).get("code") or ""))
                for item in teams
            }
            if team_code and normalize_team_code(team_code) not in codes:
                continue
            contexts.append(
                {
                    "source": "ESPN Site API",
                    "date": event.get("date", ""),
                    "eventId": event.get("id", ""),
                    "game": event.get("shortName") or event.get("name"),
                    "venue": event.get("venue", ""),
                    "city": event.get("city", ""),
                    "status": event.get("status", {}),
                    "home": event.get("home"),
                    "away": event.get("away"),
                }
            )
    except EspnApiError:
        pass
    stored = upsert_records_by_key(GAME_CONTEXT_FILE, contexts, ["source", "eventId", "date"])
    update_dataset_meta("gameContext", "ESPN Site API", len(stored))
    ballparkpal = fetch_ballparkpal_context(date, team_code) if date else {"status": "skipped", "count": 0, "reason": "Choose a game date to pull BallparkPal context."}
    return {"status": "loaded", "count": len(contexts), "storedCount": len(stored), "contexts": contexts[:8], "ballparkpal": ballparkpal}


def record_name_match(record: dict[str, Any], names: list[str], fields: list[str]) -> bool:
    targets = {clean_name(name).lower() for name in names if name}
    if not targets:
        return False
    return any(clean_name(str(record.get(field, ""))).lower() in targets for field in fields)


def record_id_match(record: dict[str, Any], ids: list[str], fields: list[str]) -> bool:
    targets = {str(value).strip().lower() for value in ids if str(value).strip()}
    if not targets:
        return False
    return any(str(record.get(field, "")).strip().lower() in targets for field in fields)


def game_context_matches(record: dict[str, Any], opponent: str, date: str) -> bool:
    if date and not str(record.get("date", "")).startswith(date):
        return False
    if not opponent:
        return bool(date)
    teams = [
        nested_get(record, ["home", "team", "abbreviation"], ""),
        nested_get(record, ["away", "team", "abbreviation"], ""),
        record.get("homeTeam", ""),
        record.get("awayTeam", ""),
    ]
    return normalize_team_code(opponent) in {normalize_team_code(str(team)) for team in teams if team}


def reset_selected_model_data(
    player: Player | None,
    pitcher: dict[str, Any] | None,
    opponent: str,
    date: str,
    season: int,
) -> dict[str, Any]:
    player_names = [player.player] if player else []
    player_ids = [player.player_id] if player else []
    pitcher_names = [str(pitcher.get("pitcher", ""))] if pitcher else []
    pitcher_ids = [str(pitcher.get("pitcherId", "")), str(pitcher.get("key", ""))] if pitcher else []
    removed: dict[str, int] = {}

    if player:
        removed["gameLogs"] = remove_json_records(
            GAME_LOG_FILE,
            lambda record: (
                (not record.get("season") or to_int(record.get("season"), season) == season)
                and (
                    record_id_match(record, player_ids, ["playerId"])
                    or record_name_match(record, player_names, ["player", "batter"])
                )
            ),
        )
        for key, path in {
            "statcastQuality": STATCAST_QUALITY_FILE,
            "handednessSplits": HANDEDNESS_SPLITS_FILE,
            "rollingForm": ROLLING_FORM_FILE,
        }.items():
            removed[key] = removed.get(key, 0) + remove_json_records(
                path,
                lambda record: record.get("role") == "batter"
                and to_int(record.get("season"), season) == season
                and record_name_match(record, player_names, ["player", "batter"]),
            )

    if pitcher:
        removed["pitchingGameLogs"] = remove_json_records(
            PITCHING_GAME_LOG_FILE,
            lambda record: (
                (not record.get("season") or to_int(record.get("season"), season) == season)
                and (
                    record_id_match(record, pitcher_ids, ["pitcherId", "key"])
                    or record_name_match(record, pitcher_names, ["pitcher", "player"])
                )
            ),
        )
        for key, path in {
            "statcastQuality": STATCAST_QUALITY_FILE,
            "handednessSplits": HANDEDNESS_SPLITS_FILE,
            "rollingForm": ROLLING_FORM_FILE,
        }.items():
            removed[key] = removed.get(key, 0) + remove_json_records(
                path,
                lambda record: record.get("role") == "pitcher"
                and to_int(record.get("season"), season) == season
                and record_name_match(record, pitcher_names, ["player", "pitcher"]),
            )
        removed["pitchArsenal"] = remove_json_records(
            PITCH_ARSENAL_FILE,
            lambda record: to_int(record.get("season"), season) == season
            and (record_id_match(record, pitcher_ids, ["pitcherId"]) or record_name_match(record, pitcher_names, ["pitcher", "player"])),
        )

    if player and pitcher:
        removed["batterPitcherAdvanced"] = remove_json_records(
            BATTER_PITCHER_ADVANCED_FILE,
            lambda record: to_int(record.get("season"), season) == season
            and (record_name_match(record, player_names, ["batter"]) or record_id_match(record, player_ids, ["batterId"]))
            and (record_name_match(record, pitcher_names, ["pitcher"]) or record_id_match(record, pitcher_ids, ["pitcherId"])),
        )

    if date or opponent:
        removed["gameContext"] = remove_json_records(GAME_CONTEXT_FILE, lambda record: game_context_matches(record, opponent, date))
        removed["ballparkContext"] = remove_json_records(BALLPARK_CONTEXT_FILE, lambda record: game_context_matches(record, opponent, date))

    for key, path in {
        "gameLogs": GAME_LOG_FILE,
        "pitchingGameLogs": PITCHING_GAME_LOG_FILE,
        "batterPitcherAdvanced": BATTER_PITCHER_ADVANCED_FILE,
        "statcastQuality": STATCAST_QUALITY_FILE,
        "handednessSplits": HANDEDNESS_SPLITS_FILE,
        "rollingForm": ROLLING_FORM_FILE,
        "pitchArsenal": PITCH_ARSENAL_FILE,
        "gameContext": GAME_CONTEXT_FILE,
        "ballparkContext": BALLPARK_CONTEXT_FILE,
    }.items():
        if removed.get(key):
            update_dataset_meta(key, f"reset before MLB/Savant/ESPN refresh ({season})", len(load_json_file(path, [])))

    return {"status": "reset", "removed": removed, "count": sum(removed.values())}


def refresh_team_game_log_sources(team_codes: list[str]) -> dict[str, Any]:
    codes = {normalize_team_code(code) for code in team_codes if normalize_team_code(code)}
    if not codes:
        return {"status": "skipped", "count": 0, "reason": "No selected team code."}
    sources = [
        source
        for source in load_dataset_sources()
        if source.get("type") == "teamGameLogs" and team_from_dataset_url(str(source.get("url", ""))) in codes
    ]
    results = []
    for source in sources:
        try:
            payload = refresh_dataset_sources(str(source.get("id", "")))
            results.extend(payload.get("results", []))
        except Exception as error:
            results.append({"id": source.get("id", ""), "type": "teamGameLogs", "status": "error", "error": str(error)})
    return {"status": "loaded" if results else "skipped", "count": len(results), "teams": sorted(codes), "results": results[:8]}


def refresh_model_data(query: dict[str, list[str]]) -> dict[str, Any]:
    season = to_int(query.get("season", [str(current_season())])[0], current_season())
    player_id = query.get("playerId", [""])[0]
    pitcher_key = query.get("pitcherKey", [""])[0]
    pitcher_name_query = query.get("pitcherName", [""])[0].strip()
    opponent = normalize_team_code(query.get("opponent", [""])[0])
    date = query.get("date", [""])[0]
    player = selected_player_by_id(player_id) if player_id else None
    pitcher = next((item for item in load_pitcher_options() if item.get("key") == pitcher_key), None)
    if not pitcher and pitcher_name_query:
        pitcher = {"pitcher": clean_name(pitcher_name_query), "pitcherId": "", "team": ""}
    results: list[dict[str, Any]] = []

    if query.get("reset", ["0"])[0].strip().lower() in {"1", "true", "yes", "on"}:
        results.append({"task": "Reset selected model data", **reset_selected_model_data(player, pitcher, opponent, date, season)})

    if query.get("teamLogs", ["0"])[0].strip().lower() in {"1", "true", "yes", "on"}:
        team_codes = [opponent]
        if player:
            team_codes.append(player.team)
        if pitcher:
            team_codes.append(str(pitcher.get("team", "")))
        results.append({"task": "Refresh saved team game-log URLs", **refresh_team_game_log_sources(team_codes)})

    if player:
        try:
            results.append({"task": "MLB batter season update", **mlb_player_lookup(player.player, season, True)})
        except MlbStatsApiError as error:
            results.append({"task": "MLB batter season update", "status": "error", "error": error.message})
        try:
            results.append({"task": "Batter game logs by opponent", **refresh_batter_game_logs_from_mlb(player.player, season, player.player_id)})
        except Exception as error:
            results.append({"task": "Batter game logs by opponent", "status": "error", "error": str(error)})
        try:
            results.append({"task": "Batter Statcast quality/splits/rolling form", **refresh_statcast_context_for_player(player.player, "batter", season)})
        except Exception as error:
            results.append({"task": "Batter Statcast quality/splits/rolling form", "status": "error", "error": str(error)})

    if pitcher:
        pitcher_name = pitcher.get("pitcher", "")
        try:
            results.append({"task": "MLB pitcher season update", **mlb_player_lookup(pitcher_name, season, True)})
        except MlbStatsApiError as error:
            results.append({"task": "MLB pitcher season update", "status": "error", "error": error.message})
        try:
            results.append(
                {
                    "task": "Pitching game logs by opponent",
                    **refresh_pitching_game_logs_from_mlb(pitcher_name, season, str(pitcher.get("pitcherId", ""))),
                }
            )
        except Exception as error:
            results.append({"task": "Pitching game logs by opponent", "status": "error", "error": str(error)})
        try:
            results.append({"task": "Pitcher Statcast quality/splits/rolling form/arsenal", **refresh_statcast_context_for_player(pitcher_name, "pitcher", season)})
        except Exception as error:
            results.append({"task": "Pitcher Statcast quality/splits/rolling form/arsenal", "status": "error", "error": str(error)})

    if player and pitcher:
        try:
            results.append({"task": "Batter vs pitcher matchup", **refresh_batter_pitcher_matchup_data(player.player, pitcher.get("pitcher", ""), season)})
        except Exception as error:
            results.append({"task": "Batter vs pitcher matchup", "status": "error", "error": str(error)})

    if date or opponent:
        try:
            results.append({"task": "Game context, starters, BallparkPal park/weather", **refresh_game_context(date, opponent)})
        except Exception as error:
            results.append({"task": "Game context, starters, BallparkPal park/weather", "status": "error", "error": str(error)})

    return {
        "season": season,
        "results": results,
        "datasets": load_dataset_meta(),
        "datasetSources": load_dataset_sources(),
        "pitchers": load_pitcher_options(),
        "dataNeeds": model_data_needs(),
        "sourceCapabilities": source_capability_map(),
    }


def csv_text_from_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def prop_input_rows(input_type: str, raw_text: str) -> tuple[list[dict[str, Any]], str]:
    text = raw_text.strip()
    if not text:
        raise ValueError("Paste prop odds CSV or OCR text first.")
    if input_type == "strikeout-odds-text":
        import image_data_importer

        rows = image_data_importer.parse_strikeout_odds_text(text)
        if not rows:
            raise ValueError("No strikeout ladder odds found in the pasted OCR text.")
        return rows, csv_text_from_rows(rows)
    rows = [dict(row) for row in normalize_rows(text)]
    if not rows:
        raise ValueError("No prop odds rows found. Use CSV columns such as Market, Player, Team, Opponent, Line, Odds, and Book.")
    return rows, csv_text_from_rows(rows)


def prop_board_report_paths(date_text: str, picks: list[dict[str, Any]], parlays: list[dict[str, Any]], notes: list[str], warnings: list[str]) -> dict[str, str]:
    import mlb_prop_analyzer as analyzer

    out_dir = DATA_DIR / "prop_reports" / "web" / date_text
    out_dir.mkdir(parents=True, exist_ok=True)
    best_value = sorted(picks, key=lambda row: (row["expected_value_per_unit"], row["edge"]), reverse=True)
    highest_probability = sorted(picks, key=lambda row: row["model_probability"], reverse=True)
    analyzer.write_csv(out_dir / "best_value.csv", best_value, analyzer.PICK_FIELDS)
    analyzer.write_csv(out_dir / "highest_probability.csv", highest_probability, analyzer.PICK_FIELDS)
    analyzer.write_csv(out_dir / "all_props.csv", picks, analyzer.PICK_FIELDS)
    analyzer.write_csv(out_dir / "parlays.csv", parlays, analyzer.PARLAY_FIELDS)
    analyzer.write_report(out_dir / "report.md", date_text, picks, parlays, notes, warnings)
    return {
        "directory": str(out_dir),
        "report": str(out_dir / "report.md"),
        "bestValue": str(out_dir / "best_value.csv"),
        "highestProbability": str(out_dir / "highest_probability.csv"),
        "allProps": str(out_dir / "all_props.csv"),
        "parlays": str(out_dir / "parlays.csv"),
    }


def analyze_prop_board_payload(payload: dict[str, Any]) -> dict[str, Any]:
    import mlb_prop_analyzer as analyzer

    input_type = str(payload.get("inputType") or "prop-odds-csv")
    rows, normalized_csv = prop_input_rows(input_type, str(payload.get("oddsText") or ""))
    props = analyzer.parse_prop_rows(rows, input_type)
    if not props:
        raise ValueError("No supported props found. This analyzer currently supports home run and pitcher strikeout markets.")

    date_text = analyzer.schedule_date_text(str(payload.get("date") or "today"))
    recent_games = max(to_int(payload.get("recentGames"), 5), 1)
    max_parlay_legs = min(max(to_int(payload.get("maxParlayLegs"), 3), 2), 5)
    parlay_pool = min(max(to_int(payload.get("parlayPool"), 12), 2), 40)
    parlay_count = min(max(to_int(payload.get("parlayCount"), 25), 1), 100)
    overrides = analyzer.ContextOverrides()
    schedule, notes = analyzer.statsapi_schedule(date_text)
    schedule = analyzer.apply_schedule_overrides(schedule, overrides)
    data = analyzer.AnalyzerData.from_app()
    picks, warnings = analyzer.analyze_props(props, data, schedule, overrides, recent_games)
    best_value = sorted(picks, key=lambda row: (row["expected_value_per_unit"], row["edge"]), reverse=True)
    highest_probability = sorted(picks, key=lambda row: row["model_probability"], reverse=True)
    parlays = analyzer.parlay_rows([row for row in picks if row["model_probability"] > 0], max_parlay_legs, parlay_pool, parlay_count)
    report_paths = prop_board_report_paths(date_text, picks, parlays, notes, warnings)
    return {
        "date": date_text,
        "inputType": input_type,
        "propCount": len(props),
        "analyzedCount": len(picks),
        "scheduleCount": len(schedule),
        "notes": notes,
        "warnings": warnings,
        "normalizedCsv": normalized_csv,
        "bestValue": best_value[:50],
        "highestProbability": highest_probability[:50],
        "allProps": picks[:100],
        "parlays": parlays[:50],
        "reportPaths": report_paths,
    }


def parse_ocr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    import image_data_importer

    parser_type = str(payload.get("type") or "strikeout-odds")
    text = str(payload.get("text") or "")
    parsers = {
        "strikeout-odds": image_data_importer.parse_strikeout_odds_text,
        "daily-strikeouts": image_data_importer.parse_daily_strikeouts_text,
        "hr-sheet": image_data_importer.parse_hr_sheet_text,
    }
    parser = parsers.get(parser_type)
    if not parser:
        raise ValueError("Unsupported OCR parser type.")
    rows = parser(text)
    return {"type": parser_type, "count": len(rows), "rows": rows, "csv": csv_text_from_rows(rows)}


def prediction_context(player: Player, opponent_code: str, matchup_adjustment: float, pitcher_key: str, date: str = "") -> dict[str, Any]:
    ab_per_game = player.at_bats / player.games if player.games else 3.8
    pa_per_game = player.plate_appearances / player.games if player.games else ab_per_game + 0.5
    contact_rate = 1 - (player.strikeouts / player.plate_appearances) if player.plate_appearances else 0.72
    walk_rate = player.walks / player.plate_appearances if player.plate_appearances else 0.08
    opponents = load_opponents()
    game_logs = load_game_logs()
    pitchers = load_pitcher_options()
    auto_adjustment, opponent_stats = opponent_adjustment(opponent_code, opponents)
    team_pitching_adj, team_pitching_stats = team_pitching_adjustment(opponent_code)
    log_adjustment, matchup_log = game_log_matchup(player, opponent_code, game_logs)
    pitcher_adj, pitcher_stats = pitcher_adjustment(pitcher_key, pitchers)
    pitcher_game_log = pitching_game_log_summary(pitcher_stats, load_pitching_game_logs(), opponent_code)
    pitcher_game_log_adj = pitching_game_log_adjustment(pitcher_game_log)
    exact_matchup = batter_pitcher_matchup(player, pitcher_stats)
    team_adj, team_stats = team_context_adjustment(opponent_code)
    recent = batter_recent_form(player, opponent_code, game_logs)
    team_matchup = team_matchup_summary(player.team, opponent_code)
    team_game_adj = team_game_log_adjustment(team_matchup)
    advanced_batter = advanced_batter_context(player, pitcher_stats)
    advanced_pitcher = advanced_pitcher_context(pitcher_stats)
    environment = ballpark_environment_context(player.team, opponent_code, date)
    advanced_adj = to_float(advanced_batter.get("totalAdjustment")) + to_float(advanced_pitcher.get("totalAdjustment"))
    environment_adj = to_float(environment.get("adjustment"))
    total_adjustment = (
        matchup_adjustment
        + auto_adjustment
        + team_pitching_adj
        + log_adjustment
        + pitcher_adj
        + pitcher_game_log_adj
        + team_adj
        + team_game_adj
        + advanced_adj
        + environment_adj
    )
    return {
        "player": player,
        "abPerGame": ab_per_game,
        "paPerGame": pa_per_game,
        "contactRate": contact_rate,
        "walkRate": walk_rate,
        "totalAdjustment": total_adjustment,
        "opponent": {
            "code": opponent_code,
            "name": TEAM_NAMES.get(opponent_code, opponent_code or "Neutral opponent"),
            "manualAdjustment": matchup_adjustment,
            "opponentDataAdjustment": round(auto_adjustment, 1),
            "teamPitchingAdjustment": round(team_pitching_adj, 1),
            "gameLogAdjustment": round(log_adjustment, 1),
            "pitcherAdjustment": round(pitcher_adj, 1),
            "pitchingGameLogAdjustment": round(pitcher_game_log_adj, 1),
            "teamBattingAdjustment": round(team_adj, 1),
            "teamGameLogAdjustment": round(team_game_adj, 1),
            "advancedBatterAdjustment": round(to_float(advanced_batter.get("totalAdjustment")), 1),
            "advancedPitcherAdjustment": round(to_float(advanced_pitcher.get("totalAdjustment")), 1),
            "environmentAdjustment": round(environment_adj, 1),
            "totalAdjustment": round(total_adjustment, 1),
            "stats": opponent_stats,
            "matchupLog": matchup_log,
            "pitcher": pitcher_stats,
            "pitchingGameLog": pitcher_game_log,
            "batterPitcher": exact_matchup,
            "teamBatting": team_stats,
            "teamPitching": team_pitching_stats,
            "teamMatchup": team_matchup,
            "advancedBatter": advanced_batter,
            "advancedPitcher": advanced_pitcher,
            "environment": environment,
        },
        "recent": recent,
    }


def hit_prediction(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    player: Player = context["player"]
    exact_matchup = context["opponent"].get("batterPitcher") or {}
    contact_rate = context["contactRate"]
    walk_rate = context["walkRate"]
    quality_bonus = clamp((player.ops - 0.720) * 0.16, -0.045, 0.055)
    discipline_bonus = clamp((contact_rate - 0.72) * 0.08 - (walk_rate - 0.085) * 0.03, -0.025, 0.025)
    adjusted_ba = clamp(player.batting_average + quality_bonus + discipline_bonus, 0.08, 0.42)
    matchup_ba = exact_matchup.get("xba") or exact_matchup.get("battingAverage") or 0.0
    adjusted_ba = clamp(blend_rate(adjusted_ba, matchup_ba, exact_matchup.get("plateAppearances", 0)), 0.08, 0.42)
    advanced = context["opponent"].get("advancedBatter") or {}
    batter_quality = advanced.get("quality") or {}
    batter_split = advanced.get("handedness") or {}
    if batter_quality.get("xba"):
        adjusted_ba = clamp(blend_rate(adjusted_ba, batter_quality["xba"], batter_quality.get("plateAppearances", 0), 0.22), 0.08, 0.42)
    if batter_split.get("battingAverage") or batter_split.get("xba"):
        adjusted_ba = clamp(blend_rate(adjusted_ba, batter_split.get("xba") or batter_split.get("battingAverage"), batter_split.get("plateAppearances", 0), 0.20), 0.08, 0.42)
    opponent_factor = clamp(1 + context["totalAdjustment"] / 100, 0.72, 1.28)
    environment = context["opponent"].get("environment") or {}
    expected_abs = clamp(context["abPerGame"] * opponent_factor * to_float(environment.get("hitFactor"), 1.0), 2.2, 5.2)
    expected = adjusted_ba * expected_abs
    prediction = {
        "target": "hits",
        "expected": round(expected, 2),
        "probabilityOnePlus": round(1 - math.pow(1 - adjusted_ba, expected_abs), 3),
        "probabilityTwoPlus": round(probability_at_least(expected, 2), 3),
        "probabilityThreePlus": round(probability_at_least(expected, 3), 3),
        "cards": [
            {"label": "Chance of 1+ hit", "value": round(1 - math.pow(1 - adjusted_ba, expected_abs), 3), "format": "percent"},
            {"label": "Expected hits", "value": round(expected, 2), "format": "number"},
            {"label": "Chance of 2+ hits", "value": round(probability_at_least(expected, 2), 3), "format": "percent"},
        ],
    }
    inputs = {
        "adjustedBattingAverage": round(adjusted_ba, 3),
        "expectedOpportunities": round(expected_abs, 2),
        "matchupPlateAppearances": exact_matchup.get("plateAppearances", 0),
        "matchupWoba": round(exact_matchup.get("woba", 0), 3),
        "matchupXwoba": round(exact_matchup.get("xwoba", 0), 3),
        "statcastXba": round(batter_quality.get("xba", 0), 3),
        "environmentHitFactor": round(to_float(environment.get("hitFactor"), 1.0), 3),
    }
    return prediction, inputs


def total_bases_prediction(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    player: Player = context["player"]
    exact_matchup = context["opponent"].get("batterPitcher") or {}
    pitcher = context["opponent"].get("pitcher") or {}
    team_pitching = context["opponent"].get("teamPitching") or {}
    batting_against = team_pitching.get("battingAgainst") or {}

    derived_slugging = player.total_bases / player.at_bats if player.at_bats and player.total_bases else 0.0
    base_slugging = player.slugging or derived_slugging or 0.390
    allowed_slugging = pitcher.get("sluggingAllowed") or batting_against.get("sluggingAllowed") or 0.0
    quality_bonus = clamp((player.ops - 0.720) * 0.08 + (context["contactRate"] - 0.72) * 0.035, -0.055, 0.075)
    adjusted_slugging = clamp(base_slugging + quality_bonus, 0.12, 0.82)
    if allowed_slugging:
        adjusted_slugging = clamp(adjusted_slugging * 0.72 + allowed_slugging * 0.28, 0.12, 0.82)

    matchup_slugging = exact_matchup.get("xslg") or exact_matchup.get("slugging") or 0.0
    adjusted_slugging = clamp(blend_rate(adjusted_slugging, matchup_slugging, exact_matchup.get("plateAppearances", 0), 0.34), 0.12, 0.82)
    advanced = context["opponent"].get("advancedBatter") or {}
    batter_quality = advanced.get("quality") or {}
    if batter_quality.get("xslg"):
        adjusted_slugging = clamp(blend_rate(adjusted_slugging, batter_quality["xslg"], batter_quality.get("plateAppearances", 0), 0.24), 0.12, 0.82)
    opponent_factor = clamp(1 + context["totalAdjustment"] / 115, 0.76, 1.3)
    environment = context["opponent"].get("environment") or {}
    expected_abs = clamp(context["abPerGame"] * opponent_factor * to_float(environment.get("hitFactor"), 1.0), 2.2, 5.2)
    expected = adjusted_slugging * expected_abs
    prediction = {
        "target": "totalBases",
        "expected": round(expected, 2),
        "probabilityOnePlus": round(probability_at_least(expected, 1), 3),
        "probabilityTwoPlus": round(probability_at_least(expected, 2), 3),
        "probabilityThreePlus": round(probability_at_least(expected, 3), 3),
    }
    inputs = {
        "adjustedSlugging": round(adjusted_slugging, 3),
        "expectedOpportunities": round(expected_abs, 2),
        "allowedSlugging": round(allowed_slugging, 3),
        "matchupPlateAppearances": exact_matchup.get("plateAppearances", 0),
        "matchupXslg": round(exact_matchup.get("xslg", 0), 3),
        "statcastXslg": round(batter_quality.get("xslg", 0), 3),
        "environmentHitFactor": round(to_float(environment.get("hitFactor"), 1.0), 3),
    }
    return prediction, inputs


def home_run_prediction(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    player: Player = context["player"]
    exact_matchup = context["opponent"].get("batterPitcher") or {}
    pitcher = context["opponent"].get("pitcher") or {}
    team_pitching = context["opponent"].get("teamPitching") or {}
    standard = team_pitching.get("standardPitching") or {}
    batting_against = team_pitching.get("battingAgainst") or {}
    advanced = team_pitching.get("advancedPitching") or {}

    player_hr_rate = player.home_runs / player.plate_appearances if player.plate_appearances else 0.025
    pitcher_hr_rate = 0.0
    if pitcher.get("homeRunsAllowed") and pitcher.get("battersFaced"):
        pitcher_hr_rate = pitcher["homeRunsAllowed"] / pitcher["battersFaced"]
    elif pitcher.get("homeRunsAllowed") and pitcher.get("atBats"):
        pitcher_hr_rate = pitcher["homeRunsAllowed"] / pitcher["atBats"]
    elif pitcher.get("homeRunRate"):
        pitcher_hr_rate = pitcher["homeRunRate"]

    team_hr_rate = 0.0
    if standard.get("homeRunsAllowed") and standard.get("innings"):
        team_hr_rate = standard["homeRunsAllowed"] / (standard["innings"] * 4.25)
    elif batting_against.get("homeRunsAllowed") and batting_against.get("plateAppearances"):
        team_hr_rate = batting_against["homeRunsAllowed"] / batting_against["plateAppearances"]
    elif advanced.get("homeRunRate"):
        team_hr_rate = advanced["homeRunRate"]

    allowed_rate = pitcher_hr_rate or team_hr_rate or 0.028
    power_bonus = clamp((player.slugging - 0.410) * 0.045 + (player.ops - 0.720) * 0.025, -0.012, 0.018)
    adjusted_hr_rate = clamp((player_hr_rate * 0.68 + allowed_rate * 0.32) + power_bonus, 0.002, 0.12)
    matchup_hr_rate = exact_matchup.get("homeRuns", 0) / exact_matchup.get("plateAppearances", 1) if exact_matchup.get("plateAppearances") else 0.0
    if not matchup_hr_rate and exact_matchup.get("barrelRate"):
        matchup_hr_rate = exact_matchup["barrelRate"] * 0.45
    adjusted_hr_rate = clamp(blend_rate(adjusted_hr_rate, matchup_hr_rate, exact_matchup.get("plateAppearances", 0), 0.32), 0.002, 0.12)
    advanced = context["opponent"].get("advancedBatter") or {}
    batter_quality = advanced.get("quality") or {}
    if batter_quality.get("barrelRate"):
        adjusted_hr_rate = clamp(blend_rate(adjusted_hr_rate, batter_quality["barrelRate"] * 0.44, batter_quality.get("battedBalls", 0), 0.18), 0.002, 0.12)
    environment = context["opponent"].get("environment") or {}
    expected_pa = clamp(context["paPerGame"] * (1 + context["totalAdjustment"] / 250), 2.8, 5.6)
    adjusted_hr_rate = clamp(adjusted_hr_rate * to_float(environment.get("homeRunFactor"), 1.0), 0.002, 0.14)
    expected = adjusted_hr_rate * expected_pa
    prediction = {
        "target": "homeRuns",
        "expected": round(expected, 2),
        "probabilityOnePlus": round(probability_at_least(expected, 1), 3),
        "probabilityTwoPlus": round(probability_at_least(expected, 2), 3),
        "probabilityThreePlus": round(probability_at_least(expected, 3), 3),
        "cards": [
            {"label": "Chance of HR", "value": round(probability_at_least(expected, 1), 3), "format": "percent"},
            {"label": "Expected HR", "value": round(expected, 2), "format": "number"},
            {"label": "Chance of 2+ HR", "value": round(probability_at_least(expected, 2), 3), "format": "percent"},
        ],
    }
    inputs = {
        "playerHomeRunRate": round(player_hr_rate, 3),
        "allowedHomeRunRate": round(allowed_rate, 3),
        "adjustedHomeRunRate": round(adjusted_hr_rate, 3),
        "expectedOpportunities": round(expected_pa, 2),
        "matchupPlateAppearances": exact_matchup.get("plateAppearances", 0),
        "matchupBarrelRate": round(exact_matchup.get("barrelRate", 0), 3),
        "statcastBarrelRate": round(batter_quality.get("barrelRate", 0), 3),
        "environmentHomeRunFactor": round(to_float(environment.get("homeRunFactor"), 1.0), 3),
    }
    return prediction, inputs


def strikeout_prediction(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    player: Player = context["player"]
    exact_matchup = context["opponent"].get("batterPitcher") or {}
    pitcher = context["opponent"].get("pitcher") or {}
    team_pitching = context["opponent"].get("teamPitching") or {}
    standard = team_pitching.get("standardPitching") or {}
    advanced = team_pitching.get("advancedPitching") or {}
    batting_against = team_pitching.get("battingAgainst") or {}

    batter_k_rate = player.strikeouts / player.plate_appearances if player.plate_appearances else 0.22
    pitcher_k_rate = pitcher.get("strikeoutRate") or 0.0
    if not pitcher_k_rate and pitcher.get("strikeouts") and pitcher.get("battersFaced"):
        pitcher_k_rate = pitcher["strikeouts"] / pitcher["battersFaced"]
    team_k_rate = advanced.get("strikeoutRate") or 0.0
    if not team_k_rate and standard.get("strikeouts") and standard.get("innings"):
        team_k_rate = standard["strikeouts"] / (standard["innings"] * 4.25)
    if not team_k_rate and batting_against.get("strikeouts") and batting_against.get("plateAppearances"):
        team_k_rate = batting_against["strikeouts"] / batting_against["plateAppearances"]

    pitcher_context_rate = pitcher_k_rate or team_k_rate or 0.225
    adjusted_k_rate = clamp(batter_k_rate * 0.58 + pitcher_context_rate * 0.42, 0.05, 0.48)
    matchup_k_rate = exact_matchup.get("strikeouts", 0) / exact_matchup.get("plateAppearances", 1) if exact_matchup.get("plateAppearances") else 0.0
    if not matchup_k_rate and exact_matchup.get("whiffRate"):
        matchup_k_rate = exact_matchup["whiffRate"] * 0.72
    adjusted_k_rate = clamp(blend_rate(adjusted_k_rate, matchup_k_rate, exact_matchup.get("plateAppearances", 0), 0.35), 0.05, 0.48)
    advanced = context["opponent"].get("advancedBatter") or {}
    batter_quality = advanced.get("quality") or {}
    batter_split = advanced.get("handedness") or {}
    if batter_quality.get("strikeoutRate"):
        adjusted_k_rate = clamp(blend_rate(adjusted_k_rate, batter_quality["strikeoutRate"], batter_quality.get("plateAppearances", 0), 0.20), 0.05, 0.48)
    if batter_split.get("strikeoutRate"):
        adjusted_k_rate = clamp(blend_rate(adjusted_k_rate, batter_split["strikeoutRate"], batter_split.get("plateAppearances", 0), 0.20), 0.05, 0.48)
    environment = context["opponent"].get("environment") or {}
    adjusted_k_rate = clamp(adjusted_k_rate * to_float(environment.get("strikeoutFactor"), 1.0), 0.05, 0.48)
    expected_pa = clamp(context["paPerGame"], 2.8, 5.6)
    expected = adjusted_k_rate * expected_pa
    prediction = {
        "target": "strikeouts",
        "expected": round(expected, 2),
        "probabilityOnePlus": round(probability_at_least(expected, 1), 3),
        "probabilityTwoPlus": round(probability_at_least(expected, 2), 3),
        "probabilityThreePlus": round(probability_at_least(expected, 3), 3),
        "cards": [
            {"label": "Chance of 1+ K", "value": round(probability_at_least(expected, 1), 3), "format": "percent"},
            {"label": "Expected Ks", "value": round(expected, 2), "format": "number"},
            {"label": "Chance of 2+ Ks", "value": round(probability_at_least(expected, 2), 3), "format": "percent"},
        ],
    }
    inputs = {
        "batterStrikeoutRate": round(batter_k_rate, 3),
        "pitcherStrikeoutRate": round(pitcher_context_rate, 3),
        "adjustedStrikeoutRate": round(adjusted_k_rate, 3),
        "expectedOpportunities": round(expected_pa, 2),
        "matchupPlateAppearances": exact_matchup.get("plateAppearances", 0),
        "matchupWhiffRate": round(exact_matchup.get("whiffRate", 0), 3),
        "statcastStrikeoutRate": round(batter_quality.get("strikeoutRate", 0), 3),
        "environmentStrikeoutFactor": round(to_float(environment.get("strikeoutFactor"), 1.0), 3),
    }
    return prediction, inputs


def pitcher_strikeout_rate(pitcher: dict[str, Any]) -> float:
    if pitcher.get("strikeoutRate"):
        return clamp(pitcher["strikeoutRate"], 0.03, 0.52)
    if pitcher.get("strikeouts") and pitcher.get("battersFaced"):
        return clamp(pitcher["strikeouts"] / pitcher["battersFaced"], 0.03, 0.52)
    if pitcher.get("strikeouts") and pitcher.get("plateAppearances"):
        return clamp(pitcher["strikeouts"] / pitcher["plateAppearances"], 0.03, 0.52)
    if pitcher.get("strikeouts") and pitcher.get("innings"):
        return clamp(pitcher["strikeouts"] / (pitcher["innings"] * 4.25), 0.03, 0.52)
    return 0.225


def pitcher_workload(pitcher: dict[str, Any]) -> tuple[float, float]:
    innings = pitcher.get("innings", 0.0) or 0.0
    starts = pitcher.get("gamesStarted", 0) or 0
    games = pitcher.get("games", 0) or 0
    batters_faced = pitcher.get("battersFaced", 0) or pitcher.get("plateAppearances", 0) or 0

    if starts > 0:
        innings_per_outing = innings / starts if innings else 5.3
        batters_per_outing = batters_faced / starts if batters_faced else innings_per_outing * 4.25
    elif games > 0:
        innings_per_outing = innings / games if innings else 4.6
        batters_per_outing = batters_faced / games if batters_faced else innings_per_outing * 4.25
    else:
        innings_per_outing = 5.2
        batters_per_outing = 22.0

    innings_per_outing = clamp(innings_per_outing, 1.0, 7.4)
    batters_per_outing = clamp(batters_per_outing, 3.0, 32.0)
    return innings_per_outing, batters_per_outing


def opposing_team_batter_profile(opponent_code: str) -> dict[str, Any]:
    team = next((item for item in load_team_batting() if item.get("team") == opponent_code), None)
    players = [player for player in load_players() if normalize_team_code(player.team) == opponent_code]

    team_rate = 0.0
    team_pa_per_game = 38.0
    if team:
        plate_appearances = team.get("plateAppearances", 0) or 0
        strikeouts = team.get("strikeouts", 0) or 0
        games = team.get("games", 0) or 0
        if plate_appearances and strikeouts:
            team_rate = strikeouts / plate_appearances
        if plate_appearances and games:
            team_pa_per_game = plate_appearances / games

    player_pas = sum(player.plate_appearances for player in players)
    player_strikeouts = sum(player.strikeouts for player in players)
    player_rate = player_strikeouts / player_pas if player_pas and player_strikeouts else 0.0

    if team_rate and player_rate:
        strikeout_rate = team_rate * 0.68 + player_rate * 0.32
    else:
        strikeout_rate = team_rate or player_rate or 0.225

    return {
        "team": team,
        "players": players,
        "teamStrikeoutRate": clamp(team_rate, 0.08, 0.34) if team_rate else 0.0,
        "playerStrikeoutRate": clamp(player_rate, 0.08, 0.34) if player_rate else 0.0,
        "strikeoutRate": clamp(strikeout_rate, 0.08, 0.34),
        "plateAppearancesPerGame": clamp(team_pa_per_game, 30.0, 46.0),
    }


def opponent_batter_strikeout_matchups(
    opponent_code: str,
    pitcher_k_rate: float,
    expected_batters_faced: float,
    opponent_k_rate: float,
) -> list[dict[str, Any]]:
    players = [
        player
        for player in load_players()
        if normalize_team_code(player.team) == opponent_code and player.plate_appearances > 0
    ]
    expected_pas_per_lineup_spot = clamp(expected_batters_faced / 9, 1.0, 3.6)
    matchups = []
    for player in players:
        batter_k_rate = player.strikeouts / player.plate_appearances if player.plate_appearances else opponent_k_rate
        matchup_rate = clamp(pitcher_k_rate * 0.56 + batter_k_rate * 0.44, 0.04, 0.58)
        expected_pa = clamp(min(player.plate_appearances / player.games if player.games else 3.8, expected_pas_per_lineup_spot), 1.0, 3.6)
        expected = matchup_rate * expected_pa
        matchups.append(
            {
                "player": player.player,
                "team": player.team,
                "plateAppearancesPerGame": round(player.plate_appearances / player.games, 2) if player.games else 0.0,
                "batterStrikeoutRate": round(batter_k_rate, 3),
                "matchupStrikeoutRate": round(matchup_rate, 3),
                "expectedStrikeouts": round(expected, 2),
                "probabilityOnePlus": round(1 - math.pow(1 - matchup_rate, expected_pa), 3),
            }
        )
    return sorted(matchups, key=lambda item: (item["probabilityOnePlus"], item["expectedStrikeouts"]), reverse=True)[:12]


def pitcher_prop_context(pitcher_key: str, opponent_code: str, matchup_adjustment: float, date: str = "") -> dict[str, Any]:
    pitchers = load_pitcher_options()
    pitcher = next((item for item in pitchers if item.get("key") == pitcher_key), None)
    if not pitcher:
        raise ValueError("Pitcher not found")

    innings_per_outing, batters_per_outing = pitcher_workload(pitcher)
    pitcher_game_log = pitching_game_log_summary(pitcher, load_pitching_game_logs(), opponent_code)
    if pitcher_game_log:
        if pitcher_game_log.get("inningsPerGame"):
            innings_per_outing = clamp(innings_per_outing * 0.74 + pitcher_game_log["inningsPerGame"] * 0.26, 1.0, 7.4)
        if pitcher_game_log.get("battersFacedPerGame"):
            batters_per_outing = clamp(batters_per_outing * 0.74 + pitcher_game_log["battersFacedPerGame"] * 0.26, 3.0, 32.0)

    opponent_profile = opposing_team_batter_profile(opponent_code)
    team_matchup = team_matchup_summary(opponent_code, pitcher.get("team", ""))
    team_game_adj = team_game_log_adjustment(team_matchup)
    advanced_pitcher = advanced_pitcher_context(pitcher)
    environment = ballpark_environment_context(pitcher.get("team", ""), opponent_code, date)
    team = opponent_profile.get("team") or {}
    opportunity_factor = 1.0
    if team.get("onBase"):
        opportunity_factor += clamp((team["onBase"] - 0.315) * 0.55, -0.045, 0.055)
    if team.get("ops"):
        opportunity_factor += clamp((team["ops"] - 0.720) * 0.12, -0.04, 0.05)
    expected_batters_faced = clamp(batters_per_outing * opportunity_factor, 3.0, 33.0)
    manual_factor = clamp(1 + matchup_adjustment / 100, 0.78, 1.24)
    if team_game_adj:
        manual_factor = clamp(manual_factor * (1 + team_game_adj / 180), 0.78, 1.24)
    if advanced_pitcher.get("totalAdjustment"):
        manual_factor = clamp(manual_factor * (1 + to_float(advanced_pitcher.get("totalAdjustment")) / 220), 0.78, 1.24)

    return {
        "pitcher": pitcher,
        "opponentProfile": opponent_profile,
        "team": team,
        "pitchingGameLog": pitcher_game_log,
        "teamMatchup": team_matchup,
        "teamGameLogAdjustment": team_game_adj,
        "advancedPitcher": advanced_pitcher,
        "environment": environment,
        "manualFactor": manual_factor,
        "inningsPerOuting": innings_per_outing,
        "battersPerOuting": batters_per_outing,
        "expectedBattersFaced": expected_batters_faced,
    }


def opponent_walk_rate(opponent_profile: dict[str, Any]) -> float:
    team = opponent_profile.get("team") or {}
    plate_appearances = to_int(team.get("plateAppearances"))
    walks = to_int(team.get("walks"))
    if plate_appearances and walks:
        return clamp(walks / plate_appearances, 0.035, 0.16)
    return 0.085


def pitcher_hit_rate(pitcher: dict[str, Any]) -> float:
    if pitcher.get("hitsAllowed") and pitcher.get("battersFaced"):
        return clamp(pitcher["hitsAllowed"] / pitcher["battersFaced"], 0.08, 0.42)
    if pitcher.get("battingAverageAllowed"):
        return clamp(pitcher["battingAverageAllowed"], 0.08, 0.42)
    if pitcher.get("hitsPerNine"):
        return clamp(pitcher["hitsPerNine"] / 38.0, 0.08, 0.42)
    return 0.235


def pitcher_runs_per_inning(pitcher: dict[str, Any]) -> float:
    innings = to_float(pitcher.get("innings"))
    runs = to_int(pitcher.get("runsAllowed")) or to_int(pitcher.get("earnedRuns"))
    if innings and runs:
        return clamp(runs / innings, 0.05, 1.05)
    era = to_float(pitcher.get("era"))
    if era:
        return clamp(era / 9, 0.05, 1.05)
    return 4.35 / 9


def predict_pitcher_strikeouts(
    pitcher_key: str,
    opponent_code: str,
    matchup_adjustment: float,
    line: float = 4.5,
    odds: int = -110,
    date: str = "",
) -> dict[str, Any]:
    context = pitcher_prop_context(pitcher_key, opponent_code, matchup_adjustment, date)
    pitcher = context["pitcher"]
    pitcher_k_rate = pitcher_strikeout_rate(pitcher)
    innings_per_outing = context["inningsPerOuting"]
    pitcher_game_log = context["pitchingGameLog"]
    if pitcher_game_log:
        if pitcher_game_log.get("strikeoutRate"):
            pitcher_k_rate = clamp(pitcher_k_rate * 0.72 + pitcher_game_log["strikeoutRate"] * 0.28, 0.04, 0.52)
    opponent_profile = context["opponentProfile"]
    opponent_k_rate = opponent_profile["strikeoutRate"]

    advanced_bonus = 0.0
    if pitcher.get("kMinusBbRate"):
        advanced_bonus += clamp((pitcher["kMinusBbRate"] - 0.145) * 0.14, -0.025, 0.035)
    if pitcher.get("siera"):
        advanced_bonus += clamp((4.15 - pitcher["siera"]) * 0.01, -0.015, 0.018)
    if pitcher.get("xfip"):
        advanced_bonus += clamp((4.15 - pitcher["xfip"]) * 0.008, -0.012, 0.015)

    manual_factor = context["manualFactor"]
    environment = context["environment"]
    adjusted_k_rate = clamp((pitcher_k_rate * 0.64 + opponent_k_rate * 0.36 + advanced_bonus) * manual_factor * to_float(environment.get("strikeoutFactor"), 1.0), 0.06, 0.48)

    team = context["team"]
    expected_batters_faced = context["expectedBattersFaced"]
    expected = adjusted_k_rate * expected_batters_faced

    over_threshold = int(math.floor(line)) + 1
    stretch_threshold = over_threshold + 1
    player_matchups = opponent_batter_strikeout_matchups(opponent_code, adjusted_k_rate, expected_batters_faced, opponent_k_rate)

    prediction = {
        "target": "pitcherStrikeouts",
        "expected": round(expected, 2),
        "line": line,
        "overThreshold": over_threshold,
        "probabilityOverLine": round(probability_at_least(expected, over_threshold), 3),
        "probabilityStretch": round(probability_at_least(expected, stretch_threshold), 3),
        "cards": [
            {"label": "Expected Ks", "value": round(expected, 2), "format": "number"},
            {"label": f"Chance over {line:g} Ks", "value": round(probability_at_least(expected, over_threshold), 3), "format": "percent"},
            {"label": f"Chance of {stretch_threshold}+ Ks", "value": round(probability_at_least(expected, stretch_threshold), 3), "format": "percent"},
        ],
    }
    prediction = attach_market(prediction, line, odds, "Ks")

    total_adjustment = (manual_factor - 1) * 100 + advanced_bonus * 100 + ((to_float(environment.get("strikeoutFactor"), 1.0) - 1) * 100)
    return {
        "pitcher": pitcher,
        "target": "pitcherStrikeouts",
        "opponent": {
            "code": opponent_code,
            "name": TEAM_NAMES.get(opponent_code, opponent_code or "Neutral opponent"),
            "manualAdjustment": matchup_adjustment,
            "advancedAdjustment": round(advanced_bonus * 100, 1),
            "teamGameLogAdjustment": round(context["teamGameLogAdjustment"], 1),
            "advancedPitcherAdjustment": round(to_float((context.get("advancedPitcher") or {}).get("totalAdjustment")), 1),
            "environmentAdjustment": round((to_float(environment.get("strikeoutFactor"), 1.0) - 1) * 100, 1),
            "totalAdjustment": round(total_adjustment, 1),
            "teamStrikeoutRate": round(opponent_profile["teamStrikeoutRate"], 3),
            "playerStrikeoutRate": round(opponent_profile["playerStrikeoutRate"], 3),
            "strikeoutRate": round(opponent_k_rate, 3),
            "plateAppearancesPerGame": round(opponent_profile["plateAppearancesPerGame"], 1),
            "playerMatchups": player_matchups,
            "teamBatting": team,
            "teamMatchup": context["teamMatchup"],
            "pitchingGameLog": pitcher_game_log,
            "advancedPitcher": context.get("advancedPitcher"),
            "environment": environment,
        },
        "inputs": {
            "pitcherStrikeoutRate": round(pitcher_k_rate, 3),
            "opponentStrikeoutRate": round(opponent_k_rate, 3),
            "adjustedStrikeoutRate": round(adjusted_k_rate, 3),
            "expectedInnings": round(innings_per_outing, 2),
            "expectedBattersFaced": round(expected_batters_faced, 1),
            "pitchingGameLogStrikeoutRate": round(pitcher_game_log.get("strikeoutRate", 0.0), 3) if pitcher_game_log else 0.0,
            "pitchingGameLogGames": pitcher_game_log.get("games", 0) if pitcher_game_log else 0,
            "environmentStrikeoutFactor": round(to_float(environment.get("strikeoutFactor"), 1.0), 3),
            "line": line,
        },
        "profile": pitcher_profile(pitcher, pitcher_game_log),
        "prediction": prediction,
        "note": "Pitcher strikeout predictions combine the pitcher's K profile with the opponent team's strikeout tendency and the highest-risk opposing batters from the uploaded batting files.",
    }


def predict_pitcher_walks(
    pitcher_key: str,
    opponent_code: str,
    matchup_adjustment: float,
    line: float = 1.5,
    odds: int = -110,
    date: str = "",
) -> dict[str, Any]:
    context = pitcher_prop_context(pitcher_key, opponent_code, matchup_adjustment, date)
    pitcher = context["pitcher"]
    pitcher_bb_rate = pitcher_walk_rate(pitcher)
    pitcher_game_log = context["pitchingGameLog"]
    if pitcher_game_log and pitcher_game_log.get("walks") and pitcher_game_log.get("battersFaced"):
        recent_rate = pitcher_game_log["walks"] / pitcher_game_log["battersFaced"]
        pitcher_bb_rate = clamp(pitcher_bb_rate * 0.76 + recent_rate * 0.24, 0.015, 0.22)
    opponent_bb_rate = opponent_walk_rate(context["opponentProfile"])
    adjusted_bb_rate = clamp((pitcher_bb_rate * 0.68 + opponent_bb_rate * 0.32) * context["manualFactor"], 0.015, 0.22)
    expected = adjusted_bb_rate * context["expectedBattersFaced"]
    prediction = attach_market(
        {
            "target": "pitcherWalks",
            "expected": round(expected, 2),
        },
        line,
        odds,
        "BB",
    )
    return {
        "pitcher": pitcher,
        "target": "pitcherWalks",
        "opponent": {
            "code": opponent_code,
            "name": TEAM_NAMES.get(opponent_code, opponent_code or "Neutral opponent"),
            "manualAdjustment": matchup_adjustment,
            "advancedAdjustment": 0.0,
            "teamGameLogAdjustment": round(context["teamGameLogAdjustment"], 1),
            "advancedPitcherAdjustment": round(to_float((context.get("advancedPitcher") or {}).get("totalAdjustment")), 1),
            "environmentAdjustment": round(to_float((context.get("environment") or {}).get("adjustment")), 1),
            "totalAdjustment": round((context["manualFactor"] - 1) * 100, 1),
            "teamWalkRate": round(opponent_bb_rate, 3),
            "teamBatting": context["team"],
            "teamMatchup": context["teamMatchup"],
            "pitchingGameLog": pitcher_game_log,
            "advancedPitcher": context.get("advancedPitcher"),
            "environment": context.get("environment"),
            "playerMatchups": [],
        },
        "inputs": {
            "pitcherWalkRate": round(pitcher_bb_rate, 3),
            "opponentWalkRate": round(opponent_bb_rate, 3),
            "adjustedWalkRate": round(adjusted_bb_rate, 3),
            "expectedInnings": round(context["inningsPerOuting"], 2),
            "expectedBattersFaced": round(context["expectedBattersFaced"], 1),
            "line": line,
        },
        "profile": pitcher_profile(pitcher, pitcher_game_log),
        "prediction": prediction,
        "note": "Pitcher walk predictions combine the pitcher's walk profile, opponent walk tendency, expected batters faced, and your manual matchup adjustment.",
    }


def predict_pitcher_runs_allowed(
    pitcher_key: str,
    opponent_code: str,
    matchup_adjustment: float,
    line: float = 2.5,
    odds: int = -110,
    date: str = "",
) -> dict[str, Any]:
    context = pitcher_prop_context(pitcher_key, opponent_code, matchup_adjustment, date)
    pitcher = context["pitcher"]
    run_rate = pitcher_runs_per_inning(pitcher)
    pitcher_game_log = context["pitchingGameLog"]
    if pitcher_game_log and pitcher_game_log.get("innings"):
        recent_run_rate = (to_int(pitcher_game_log.get("runsAllowed")) or to_int(pitcher_game_log.get("earnedRuns"))) / pitcher_game_log["innings"]
        run_rate = clamp(run_rate * 0.76 + recent_run_rate * 0.24, 0.05, 1.05)
    team = context["team"]
    team_runs_per_game = to_float(team.get("runsPerGame"))
    if not team_runs_per_game and team.get("runs") and team.get("games"):
        team_runs_per_game = team["runs"] / team["games"]
    offense_factor = clamp((team_runs_per_game or 4.35) / 4.35, 0.72, 1.32)
    environment = context.get("environment") or {}
    adjusted_run_rate = clamp(run_rate * offense_factor * context["manualFactor"] * to_float(environment.get("runFactor"), 1.0), 0.04, 1.2)
    expected = adjusted_run_rate * context["inningsPerOuting"]
    prediction = attach_market(
        {
            "target": "pitcherRunsAllowed",
            "expected": round(expected, 2),
        },
        line,
        odds,
        "runs",
    )
    return {
        "pitcher": pitcher,
        "target": "pitcherRunsAllowed",
        "opponent": {
            "code": opponent_code,
            "name": TEAM_NAMES.get(opponent_code, opponent_code or "Neutral opponent"),
            "manualAdjustment": matchup_adjustment,
            "advancedAdjustment": round((offense_factor - 1) * 100, 1),
            "teamGameLogAdjustment": round(context["teamGameLogAdjustment"], 1),
            "advancedPitcherAdjustment": round(to_float((context.get("advancedPitcher") or {}).get("totalAdjustment")), 1),
            "environmentAdjustment": round((to_float(environment.get("runFactor"), 1.0) - 1) * 100, 1),
            "totalAdjustment": round((offense_factor * context["manualFactor"] * to_float(environment.get("runFactor"), 1.0) - 1) * 100, 1),
            "teamRunsPerGame": round(team_runs_per_game or 0.0, 2),
            "teamBatting": team,
            "teamMatchup": context["teamMatchup"],
            "pitchingGameLog": pitcher_game_log,
            "advancedPitcher": context.get("advancedPitcher"),
            "environment": environment,
            "playerMatchups": [],
        },
        "inputs": {
            "pitcherRunsPerInning": round(run_rate, 3),
            "opponentRunsPerGame": round(team_runs_per_game or 0.0, 2),
            "adjustedRunsPerInning": round(adjusted_run_rate, 3),
            "expectedInnings": round(context["inningsPerOuting"], 2),
            "expectedBattersFaced": round(context["expectedBattersFaced"], 1),
            "line": line,
        },
        "profile": pitcher_profile(pitcher, pitcher_game_log),
        "prediction": prediction,
        "note": "Pitcher runs allowed predictions combine pitcher run prevention, expected innings, opponent scoring profile, and your manual matchup adjustment.",
    }


def predict_pitcher_hits_allowed(
    pitcher_key: str,
    opponent_code: str,
    matchup_adjustment: float,
    line: float = 4.5,
    odds: int = -110,
    date: str = "",
) -> dict[str, Any]:
    context = pitcher_prop_context(pitcher_key, opponent_code, matchup_adjustment, date)
    pitcher = context["pitcher"]
    pitcher_h_rate = pitcher_hit_rate(pitcher)
    pitcher_game_log = context["pitchingGameLog"]
    if pitcher_game_log and pitcher_game_log.get("hitsAllowed") and pitcher_game_log.get("battersFaced"):
        recent_rate = pitcher_game_log["hitsAllowed"] / pitcher_game_log["battersFaced"]
        pitcher_h_rate = clamp(pitcher_h_rate * 0.76 + recent_rate * 0.24, 0.08, 0.42)
    team = context["team"]
    opponent_hit_rate = to_float(team.get("battingAverage")) or 0.245
    environment = context.get("environment") or {}
    adjusted_h_rate = clamp((pitcher_h_rate * 0.62 + opponent_hit_rate * 0.38) * context["manualFactor"] * to_float(environment.get("hitFactor"), 1.0), 0.08, 0.42)
    expected = adjusted_h_rate * context["expectedBattersFaced"]
    prediction = attach_market(
        {
            "target": "pitcherHitsAllowed",
            "expected": round(expected, 2),
        },
        line,
        odds,
        "hits",
    )
    return {
        "pitcher": pitcher,
        "target": "pitcherHitsAllowed",
        "opponent": {
            "code": opponent_code,
            "name": TEAM_NAMES.get(opponent_code, opponent_code or "Neutral opponent"),
            "manualAdjustment": matchup_adjustment,
            "advancedAdjustment": 0.0,
            "teamGameLogAdjustment": round(context["teamGameLogAdjustment"], 1),
            "advancedPitcherAdjustment": round(to_float((context.get("advancedPitcher") or {}).get("totalAdjustment")), 1),
            "environmentAdjustment": round((to_float(environment.get("hitFactor"), 1.0) - 1) * 100, 1),
            "totalAdjustment": round((context["manualFactor"] * to_float(environment.get("hitFactor"), 1.0) - 1) * 100, 1),
            "teamHitRate": round(opponent_hit_rate, 3),
            "teamBatting": team,
            "teamMatchup": context["teamMatchup"],
            "pitchingGameLog": pitcher_game_log,
            "advancedPitcher": context.get("advancedPitcher"),
            "environment": environment,
            "playerMatchups": [],
        },
        "inputs": {
            "pitcherHitRate": round(pitcher_h_rate, 3),
            "opponentHitRate": round(opponent_hit_rate, 3),
            "adjustedHitRate": round(adjusted_h_rate, 3),
            "expectedInnings": round(context["inningsPerOuting"], 2),
            "expectedBattersFaced": round(context["expectedBattersFaced"], 1),
            "line": line,
        },
        "profile": pitcher_profile(pitcher, pitcher_game_log),
        "prediction": prediction,
        "note": "Pitcher hits allowed predictions blend pitcher hit suppression, opponent batting average, expected batters faced, and your manual matchup adjustment.",
    }


def predict_pitcher_prop(
    target: str,
    pitcher_key: str,
    opponent_code: str,
    matchup_adjustment: float,
    line: float,
    odds: int,
    date: str = "",
) -> dict[str, Any]:
    if target == "pitcherWalks":
        return predict_pitcher_walks(pitcher_key, opponent_code, matchup_adjustment, line or 1.5, odds, date)
    if target == "pitcherRunsAllowed":
        return predict_pitcher_runs_allowed(pitcher_key, opponent_code, matchup_adjustment, line or 2.5, odds, date)
    if target == "pitcherHitsAllowed":
        return predict_pitcher_hits_allowed(pitcher_key, opponent_code, matchup_adjustment, line or 4.5, odds, date)
    return predict_pitcher_strikeouts(pitcher_key, opponent_code, matchup_adjustment, line or 4.5, odds, date)


def predict_prop(
    player: Player,
    opponent_code: str,
    matchup_adjustment: float,
    pitcher_key: str = "",
    target: str = "hits",
    line: float = 0.5,
    odds: int = -110,
    date: str = "",
) -> dict[str, Any]:
    context = prediction_context(player, opponent_code, matchup_adjustment, pitcher_key, date)
    if target == "homeRuns":
        prediction, target_inputs = home_run_prediction(context)
        unit_label = "HR"
        note = "Home run predictions combine batter HR rate, Statcast quality, rolling form, pitcher/team HR allowed, handedness context, and weather-adjusted park environment."
    elif target == "totalBases":
        prediction, target_inputs = total_bases_prediction(context)
        unit_label = "TB"
        if line <= 0:
            line = 1.5
        note = "Total bases predictions combine batter slugging power, Statcast xSLG/quality, pitcher/team slugging allowed, and weather-adjusted hit environment."
    elif target == "strikeouts":
        prediction, target_inputs = strikeout_prediction(context)
        unit_label = "Ks"
        note = "Strikeout predictions combine batter K rate with pitcher/team strikeout rates, Statcast whiff/K form, handedness splits, and environment."
    else:
        target = "hits"
        prediction, target_inputs = hit_prediction(context)
        unit_label = "hits"
        note = "Hit predictions combine batter average/contact quality, Statcast xBA/xwOBA, rolling form, handedness splits, pitcher/team batting-against, and park/weather context."
    prediction = attach_market(prediction, line, odds, unit_label)

    inputs = {
        "abPerGame": round(context["abPerGame"], 2),
        "paPerGame": round(context["paPerGame"], 2),
        "contactRate": round(context["contactRate"], 3),
        "walkRate": round(context["walkRate"], 3),
        **target_inputs,
    }
    return {
        "player": asdict(player),
        "target": target,
        "opponent": context["opponent"],
        "inputs": inputs,
        "profiles": {
            "batterHomeRuns": batter_home_run_profile(player, context),
            "pitcher": pitcher_profile(context["opponent"].get("pitcher"), context["opponent"].get("pitchingGameLog")),
            "advancedBatter": context["opponent"].get("advancedBatter"),
            "advancedPitcher": context["opponent"].get("advancedPitcher"),
            "environment": context["opponent"].get("environment"),
        },
        "recent": context.get("recent", {}),
        "prediction": prediction,
        "note": note,
    }



def game_context_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from baseball_ui_tools import game_context_payload as payload
    return payload(query)


def odds_market_signals_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from baseball_ui_tools import odds_market_signals_payload as payload
    return payload(query)


def team_props_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from baseball_ui_tools import team_props_payload as payload
    return payload(query)


def expanded_prop_search_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from baseball_ui_tools import expanded_prop_search_payload as payload
    return payload(query)


def umpire_sync_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from umpire_collector import sync_umpires
    season = int(query.get("season", ["2026"])[0])
    force_raw = query.get("force", ["0"])[0].strip().lower()
    force = force_raw not in {"0", "false", "no", ""}
    return sync_umpires(season=season, force=force)


def umpire_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    import csv
    from pathlib import Path
    season = int(query.get("season", ["2026"])[0])
    base = Path(__file__).parent / "data" / "cache" / "umpires"
    def row_count(path: Path) -> int | None:
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as handle:
            return max(sum(1 for _ in csv.reader(handle)) - 1, 0)
    stat_path = base / f"umpire_stats_{season}.csv"
    game_path = base / f"game_umpires_{season}.csv"
    return {
        "season": season,
        "umpireStatRows": row_count(stat_path),
        "gameUmpireRows": row_count(game_path),
        "statPath": str(stat_path) if stat_path.exists() else None,
        "gamePath": str(game_path) if game_path.exists() else None,
    }


def platoon_splits_sync_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from platoon_splits_collector import sync_platoon_splits
    season = int(query.get("season", ["2026"])[0])
    max_players = int(query.get("max_players", ["0"])[0])
    return sync_platoon_splits(season=season, max_players=max_players)


def platoon_splits_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    import csv
    from pathlib import Path
    season = int(query.get("season", ["2026"])[0])
    base = Path(__file__).parent / "data" / "cache" / "incremental_stats"
    def row_count(path: Path) -> int | None:
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as handle:
            return max(sum(1 for _ in csv.reader(handle)) - 1, 0)
    batter_path = base / f"batter_platoon_splits_{season}.csv"
    pitcher_path = base / f"pitcher_platoon_splits_{season}.csv"
    return {
        "season": season,
        "batterRows": row_count(batter_path),
        "pitcherRows": row_count(pitcher_path),
        "batterPath": str(batter_path) if batter_path.exists() else None,
        "pitcherPath": str(pitcher_path) if pitcher_path.exists() else None,
    }


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
        return


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if not length:
        return {}
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("Request body must be valid JSON.") from error
    return payload if isinstance(payload, dict) else {}

POST_ONLY_ENDPOINTS = {
    "/api/predictions/save",
    "/api/predictions/grade",
    "/api/savant/sync",
    "/api/odds-movement/sync",
    "/api/weather/sync",
    "/api/weather/build",
    "/api/incremental-features/build",
    "/api/incremental-features/cross-reference",
    "/api/incremental-stats/catchup",
    "/api/season-cache/backfill",
    "/api/all-data-prop/save-prediction",
    "/api/all-data-prop/build-bvp",
    "/api/pipeline/autofill-game-odds",
    "/api/daily-workflow/before",
    "/api/daily-workflow/after",
    "/api/pipeline/create-template",
    "/api/pipeline/grade",
    "/api/pipeline/merge-game-odds",
    "/api/pipeline/prepare-strikeouts",
    "/api/pipeline/train-strikeouts",
    "/api/pipeline/run-after-game",
    "/api/propline/props",
    "/api/model-data/refresh",
    "/api/umpire/sync",
    "/api/platoon-splits/sync",
}

ACTION_HEADER_NAME = "X-Baseball-Prop-Action"
ACTION_HEADER_VALUE = "1"

PROPLINE_SPORT = "baseball_mlb"
PROPLINE_MARKETS = [
    "batter_hits",
    "batter_home_runs",
    "batter_total_bases",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]


class PropLineApiError(Exception):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def propline_client() -> Any:
    api_key = os.environ.get("PROPLINE_API_KEY", "").strip()
    if not api_key:
        raise PropLineApiError("Missing PROPLINE_API_KEY in .env", 400)
    try:
        from propline import PropLine
    except ImportError as error:
        raise PropLineApiError("Install PropLine first: python -m pip install propline", 500) from error
    return PropLine(api_key)


def normalize_propline_prop(event: dict[str, Any], bookmaker: dict[str, Any], market: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": event.get("commence_time") or "",
        "eventId": event.get("id", ""),
        "game": f"{event.get('away_team', '')} @ {event.get('home_team', '')}".strip(),
        "homeTeam": event.get("home_team", ""),
        "awayTeam": event.get("away_team", ""),
        "book": bookmaker.get("title") or bookmaker.get("key") or "",
        "bookKey": bookmaker.get("key", ""),
        "market": market.get("key", ""),
        "player": outcome.get("description") or outcome.get("player") or "",
        "side": outcome.get("name", ""),
        "line": outcome.get("point", ""),
        "americanOdds": outcome.get("price", ""),
        "lastUpdate": market.get("last_update") or bookmaker.get("last_update") or "",
    }


def save_propline_props_csv(props: list[dict[str, Any]], date_label: str) -> str:
    odds_dir = DATA_DIR / "odds"
    odds_dir.mkdir(parents=True, exist_ok=True)
    path = odds_dir / f"propline_props_{date_label}.csv"

    columns = [
        "date",
        "eventId",
        "game",
        "homeTeam",
        "awayTeam",
        "book",
        "bookKey",
        "market",
        "player",
        "side",
        "line",
        "americanOdds",
        "lastUpdate",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for prop in props:
            writer.writerow({column: prop.get(column, "") for column in columns})

    return str(path)


def propline_date_from_query(query: dict[str, list[str]]) -> str:
    raw = query.get("date", [""])[0].strip()
    date_label = datetime.now().strftime("%Y-%m-%d") if raw.lower() in {"", "today"} else raw
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_label):
        raise PropLineApiError("PropLine date must be YYYY-MM-DD.", 400)
    return date_label


def propline_event_date(event: dict[str, Any]) -> str:
    raw = str(event.get("commence_time") or event.get("commenceTime") or event.get("date") or "").strip()
    return raw[:10] if re.match(r"\d{4}-\d{2}-\d{2}", raw) else ""


def propline_props_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    date_label = propline_date_from_query(query)
    from propline_value_client import (
        get_events as guarded_get_events,
        get_event_player_props,
        value_client_status,
    )
    sport = query.get("sport", [PROPLINE_SPORT])[0] or PROPLINE_SPORT
    markets_raw = query.get("markets", [",".join(PROPLINE_MARKETS)])[0]
    markets = [market.strip() for market in markets_raw.split(",") if market.strip()]
    save_csv = query.get("save", ["1"])[0].strip().lower() not in {"0", "false", "no"}

    # Tests and local diagnostics may monkeypatch app.propline_client().
    # In normal runtime, use the token-aware guarded client.
    use_mocked_client = inspect.getmodule(propline_client).__name__ != __name__
    client = propline_client() if use_mocked_client else None

    all_events = client.get_events(sport) if client else guarded_get_events(sport)
    events = [
        event
        for event in all_events
        if not propline_event_date(event) or propline_event_date(event) == date_label
    ]
    props: list[dict[str, Any]] = []

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        try:
            odds = client.get_odds(sport, event_id=event_id, markets=markets) if client else get_event_player_props(str(event_id), markets=markets, sport=sport)
        except Exception:
            continue

        for bookmaker in odds.get("bookmakers", []) or []:
            for market in bookmaker.get("markets", []) or []:
                for outcome in market.get("outcomes", []) or []:
                    props.append(normalize_propline_prop(event, bookmaker, market, outcome))

    saved_path = save_propline_props_csv(props, date_label) if save_csv else ""

    return {
        "date": date_label,
        "sport": sport,
        "markets": markets,
        "eventCount": len(events),
        "totalEventCount": len(all_events),
        "tokenGuard": value_client_status().get("tokenGuard", {}),
        "propCount": len(props),
        "savedPath": saved_path,
        "props": props[:300],
    }

class AppHandler(BaseHTTPRequestHandler):
    def handle_action_post(self, parsed: Any) -> bool:
        if parsed.path not in POST_ONLY_ENDPOINTS:
            return False

        if self.headers.get(ACTION_HEADER_NAME) != ACTION_HEADER_VALUE:
            json_response(
                self,
                {"error": f"Missing required {ACTION_HEADER_NAME} header for action endpoint."},
                HTTPStatus.FORBIDDEN,
            )
            return True

        query = parse_qs(parsed.query)

        if parsed.path == "/api/predictions/save":
            try:
                json_response(self, prediction_save_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/predictions/grade":
            try:
                json_response(self, prediction_grade_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/savant/sync":
            try:
                json_response(self, savant_sync_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/odds-movement/sync":
            try:
                json_response(self, odds_movement_sync_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/weather/sync":
            try:
                json_response(self, weather_sync_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/weather/build":
            try:
                json_response(self, weather_build_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/incremental-features/build":
            try:
                json_response(self, incremental_features_build_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/incremental-features/cross-reference":
            try:
                json_response(self, incremental_features_cross_reference_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/incremental-stats/catchup":
            try:
                json_response(self, incremental_stats_catchup_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/season-cache/backfill":
            try:
                json_response(self, season_cache_backfill_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/all-data-prop/save-prediction":
            try:
                json_response(self, save_all_data_prediction_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/all-data-prop/build-bvp":
            try:
                json_response(self, batter_pitcher_samples_payload())
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/pipeline/autofill-game-odds":
            try:
                date_label = pipeline_date_from_query(query)
                json_response(self, pipeline_autofill_game_odds(date_label))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/daily-workflow/before":
            try:
                json_response(self, daily_workflow_before_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/daily-workflow/after":
            try:
                json_response(self, daily_workflow_after_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/pipeline/create-template":
            try:
                date_label = pipeline_date_from_query(query)
                json_response(self, pipeline_create_game_odds_template(date_label))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/pipeline/grade":
            try:
                date_label = pipeline_date_from_query(query)
                json_response(self, pipeline_grade_props(date_label))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/pipeline/merge-game-odds":
            try:
                date_label = pipeline_date_from_query(query)
                json_response(self, pipeline_merge_game_odds(date_label))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/pipeline/prepare-strikeouts":
            try:
                json_response(self, pipeline_prepare_strikeouts())
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/pipeline/train-strikeouts":
            try:
                json_response(self, pipeline_train_strikeouts())
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/pipeline/run-after-game":
            try:
                date_label = pipeline_date_from_query(query)
                json_response(self, pipeline_run_after_game(date_label))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/propline/props":
            try:
                json_response(self, propline_props_payload(query))
            except PropLineApiError as error:
                json_response(self, {"error": error.message}, error.status)
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/model-data/refresh":
            try:
                json_response(self, refresh_model_data(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True


        if parsed.path == "/api/umpire/sync":
            try:
                json_response(self, umpire_sync_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        if parsed.path == "/api/platoon-splits/sync":
            try:
                json_response(self, platoon_splits_sync_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return True

        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path in POST_ONLY_ENDPOINTS:
            json_response(self, {"error": "Use POST for this action endpoint."}, HTTPStatus.METHOD_NOT_ALLOWED)
            return

        if parsed.path == "/api/model/performance":
            try:
                query = parse_qs(parsed.query)
                json_response(self, model_performance_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return



        if parsed.path == "/api/app/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, app_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return


        if parsed.path == "/api/game-context":
            try:
                query = parse_qs(parsed.query)
                json_response(self, game_context_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/odds-market-signals":
            try:
                query = parse_qs(parsed.query)
                json_response(self, odds_market_signals_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/team-props":
            try:
                query = parse_qs(parsed.query)
                json_response(self, team_props_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/prop-search-expanded":
            try:
                query = parse_qs(parsed.query)
                json_response(self, expanded_prop_search_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/umpire/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, umpire_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/platoon-splits/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, platoon_splits_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/playerboard/health":
            try:
                query = parse_qs(parsed.query)
                json_response(self, playerboard_health_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/playerboard":
            try:
                query = parse_qs(parsed.query)
                json_response(self, playerboard_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/player/profile":
            try:
                query = parse_qs(parsed.query)
                json_response(self, player_profile_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/player/search":
            try:
                query = parse_qs(parsed.query)
                json_response(self, player_search_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/player/autofill":
            try:
                query = parse_qs(parsed.query)
                json_response(self, player_autofill_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/predictions/dashboard":
            try:
                query = parse_qs(parsed.query)
                json_response(self, prediction_dashboard_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/predictions/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, prediction_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return


        if parsed.path == "/api/stage3/line-comparison":
            try:
                query = parse_qs(parsed.query)
                json_response(self, stage3_line_comparison_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/stage3/steam-alerts":
            try:
                query = parse_qs(parsed.query)
                json_response(self, stage3_steam_alerts_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/stage3/pnl-analytics":
            try:
                query = parse_qs(parsed.query)
                json_response(self, stage3_pnl_analytics_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/savant/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, savant_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/odds-movement/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, odds_movement_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/incremental-stats/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, incremental_stats_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/incremental-stats/lookup":
            try:
                query = parse_qs(parsed.query)
                json_response(self, incremental_stats_lookup_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/season-cache/status":
            try:
                query = parse_qs(parsed.query)
                json_response(self, season_cache_status_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/season-cache/lookup":
            try:
                query = parse_qs(parsed.query)
                json_response(self, season_cache_lookup_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/unified-prop-card/predict":
            try:
                query = parse_qs(parsed.query)
                json_response(self, unified_prop_card_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/saved-games":
            try:
                query = parse_qs(parsed.query)
                json_response(self, saved_games_query_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/saved-props-for-game":
            try:
                query = parse_qs(parsed.query)
                json_response(self, saved_props_for_game_query_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/saved-props":
            try:
                query = parse_qs(parsed.query)
                json_response(self, saved_props_query_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return



        if parsed.path == "/api/workflows/health":
            try:
                query = parse_qs(parsed.query)
                json_response(self, workflow_summaries_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/grading/health":
            try:
                query = parse_qs(parsed.query)
                json_response(self, grading_health_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/data-health":
            try:
                query = parse_qs(parsed.query)
                json_response(self, data_health_query_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/all-data-prop/predict":
            try:
                query = parse_qs(parsed.query)
                json_response(self, all_data_prop_query_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/daily-workflow/status":
            try:
                json_response(self, prop_ml_market_status_payload())
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/prop-ml/status":
            try:
                json_response(self, prop_ml_market_status_payload())
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/prop-ml/predict":
            try:
                query = parse_qs(parsed.query)
                json_response(self, prop_ml_prediction_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/moneyline/predict":
            try:
                query = parse_qs(parsed.query)
                json_response(self, moneyline_prediction_payload(query))
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/players":
            players = load_players()
            json_response(
                self,
                {
                    "players": [asdict(player) for player in players],
                    "teams": [{"code": code, "name": name} for code, name in sorted(TEAM_NAMES.items())],
                    "pitchers": load_pitcher_options(),
                    "datasets": load_dataset_meta(),
                    "datasetSources": load_dataset_sources(),
                    "dataNeeds": model_data_needs(),
                    "sourceCapabilities": source_capability_map(),
                    "count": len(players),
                },
            )
            return

        if parsed.path == "/api/dataset-sources":
            json_response(self, {"sources": load_dataset_sources()})
            return

        if parsed.path == "/api/model-data/sources":
            json_response(self, source_capability_map())
            return

        if parsed.path == "/api/player-recent":
            query = parse_qs(parsed.query)
            try:
                json_response(self, player_recent_payload(query.get("playerId", [""])[0], query.get("opponent", [""])[0]))
            except ValueError as error:
                json_response(self, {"error": str(error)}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/api/ballpark-context":
            query = parse_qs(parsed.query)
            team = query.get("team", [""])[0]
            opponent = query.get("opponent", [""])[0]
            date = query.get("date", [""])[0]
            json_response(self, {"environment": ballpark_environment_context(team, opponent, date), "count": len(load_ballpark_context())})
            return

        if parsed.path == "/api/predict":
            query = parse_qs(parsed.query)
            player_id = query.get("playerId", [""])[0]
            opponent = query.get("opponent", [""])[0].upper()
            pitcher_key = query.get("pitcherKey", [""])[0]
            target = query.get("target", ["hits"])[0]
            adjustment = to_float(query.get("adjustment", ["0"])[0])
            date = query.get("date", [""])[0]
            default_line = "1.5" if target == "totalBases" else "0.5"
            line = to_float(query.get("line", [default_line])[0], to_float(default_line))
            odds = to_int(query.get("odds", ["-110"])[0], -110)
            players = load_players()
            player = next((item for item in players if item.player_id == player_id), None)
            if not player:
                json_response(self, {"error": "Player not found"}, HTTPStatus.NOT_FOUND)
                return
            json_response(self, predict_prop(player, opponent, adjustment, pitcher_key, target, line, odds, date))
            return

        if parsed.path == "/api/predict-pitcher":
            query = parse_qs(parsed.query)
            opponent = query.get("opponent", [""])[0].upper()
            pitcher_key = query.get("pitcherKey", [""])[0]
            target = query.get("target", ["pitcherStrikeouts"])[0]
            adjustment = to_float(query.get("adjustment", ["0"])[0])
            date = query.get("date", [""])[0]
            default_line = {
                "pitcherWalks": "1.5",
                "pitcherRunsAllowed": "2.5",
                "pitcherHitsAllowed": "4.5",
            }.get(target, "4.5")
            line = to_float(query.get("line", [default_line])[0], to_float(default_line))
            odds = to_int(query.get("odds", ["-110"])[0], -110)
            try:
                json_response(self, predict_pitcher_prop(target, pitcher_key, opponent, adjustment, line, odds, date))
            except ValueError as error:
                json_response(self, {"error": str(error)}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/api/github":
            query = parse_qs(parsed.query)
            owner = query.get("owner", [""])[0].strip()
            repo = query.get("repo", [""])[0].strip()
            repo_full_name = query.get("repository", [""])[0].strip()
            if repo_full_name and not owner and not repo:
                owner, repo = split_repo_name(repo_full_name)
            try:
                json_response(self, github_repo_status(owner, repo))
            except GitHubApiError as error:
                json_response(self, {"error": error.message}, error.status)
            return

        if parsed.path == "/api/mlb/status":
            json_response(self, mlb_package_status())
            return

        if parsed.path == "/api/mlb/player":
            query = parse_qs(parsed.query)
            name = query.get("name", [""])[0].strip()
            season = to_int(query.get("season", [str(current_season())])[0], current_season())
            store = query.get("store", ["1"])[0].strip().lower() not in {"0", "false", "no"}
            try:
                json_response(self, mlb_player_lookup(name, season, store))
            except MlbStatsApiError as error:
                json_response(self, {"error": error.message}, error.status)
            return

        if parsed.path == "/api/mlb/command":
            query = parse_qs(parsed.query)
            command = query.get("command", [""])[0].strip()
            try:
                json_response(self, mlb_command_response(command, query))
            except MlbStatsApiError as error:
                json_response(self, {"error": error.message}, error.status)
            return

        if parsed.path == "/api/espn/scoreboard":
            query = parse_qs(parsed.query)
            params = {key: values[0] for key, values in query.items() if values}
            try:
                json_response(self, espn_scoreboard(params))
            except EspnApiError as error:
                json_response(self, {"error": error.message}, error.status)
            return

        if parsed.path == "/api/espn/teams":
            try:
                json_response(self, espn_teams())
            except EspnApiError as error:
                json_response(self, {"error": error.message}, error.status)
            return

        if parsed.path == "/api/espn/team":
            query = parse_qs(parsed.query)
            team = query.get("team", [""])[0].strip()
            try:
                json_response(self, espn_team_lookup(team))
            except EspnApiError as error:
                json_response(self, {"error": error.message}, error.status)
            return

        if parsed.path.startswith("/api/espn/teams/"):
            team = parsed.path.removeprefix("/api/espn/teams/").strip("/")
            try:
                json_response(self, espn_team_lookup(team))
            except EspnApiError as error:
                json_response(self, {"error": error.message}, error.status)
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if self.handle_action_post(parsed):
            return

        if parsed.path == "/api/refresh-sources":
            query = parse_qs(parsed.query)
            source_id = query.get("id", ["all"])[0]
            try:
                json_response(self, refresh_dataset_sources(source_id))
            except ValueError as error:
                json_response(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/prop-board/analyze":
            try:
                json_response(self, analyze_prop_board_payload(read_json_body(self)))
            except ValueError as error:
                json_response(self, {"error": str(error)}, 400)
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/ocr/parse":
            try:
                json_response(self, parse_ocr_payload(read_json_body(self)))
            except ValueError as error:
                json_response(self, {"error": str(error)}, 400)
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path == "/api/ml/predict":
            try:
                features = read_json_body(self)
                prediction = predict_from_row(features)
                json_response(self, prediction.to_dict())
            except FileNotFoundError as error:
                json_response(self, {"error": str(error)}, HTTPStatus.NOT_FOUND)
            except ValueError as error:
                json_response(self, {"error": str(error)}, 400)
            except Exception as error:
                json_response(self, {"error": str(error)}, 500)
            return

        if parsed.path not in {"/api/upload", "/api/import-url"}:
            json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        query = parse_qs(parsed.query)
        csv_type = query.get("type", ["batting"])[0]
        filename = query.get("filename", ["uploaded.csv"])[0]
        dataset_url = ""
        if parsed.path == "/api/import-url":
            dataset_url = query.get("url", [""])[0].strip()
            if not dataset_url:
                json_response(self, {"error": "Dataset URL is required."}, 400)
                return
            try:
                raw, filename = fetch_dataset_url(dataset_url)
            except ValueError as error:
                json_response(self, {"error": str(error)}, 400)
                return
        else:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8-sig", errors="replace")

        try:
            json_response(self, process_dataset_payload(csv_type, raw, filename, dataset_url))
        except ValueError as error:
            json_response(self, {"error": str(error)}, 400)

    def serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        target = (PUBLIC_DIR / relative).resolve()
        if PUBLIC_DIR.resolve() not in target.parents and target != PUBLIC_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or target.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        try:
            print(f"{self.address_string()} - {format % args}")
        except (OSError, ValueError):
            pass


def main() -> None:
    load_env_file(ROOT / ".env")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8766"))
    os.environ.setdefault("BASEBALL_PROP_APP_PORT", str(port))
    os.environ.setdefault("BASEBALL_PROP_APP_URL", f"http://127.0.0.1:{port}")
    DATA_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    start_dataset_auto_refresh()
    try:
        print(f"Baseball prop predictor running at http://127.0.0.1:{port}")
    except (OSError, ValueError):
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
