from __future__ import annotations

"""Save and grade Unified Prop Card predictions.

Files:
- data/predictions/prediction_history_2026.csv
- data/predictions/prediction_grades_2026.csv
- data/predictions/prediction_status_2026.json

Supported grading:
- batter_hits
- batter_total_bases
- batter_home_runs
- pitcher_strikeouts
- pitcher_hits_allowed
- pitcher_earned_runs
"""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PREDICTION_DIR = ROOT / "data" / "predictions"
STATS_DIR = ROOT / "data" / "cache" / "incremental_stats"

PREDICTION_FIELDS = [
    "predictionId",
    "savedAt",
    "season",
    "date",
    "market",
    "player",
    "team",
    "opponent",
    "pitcher",
    "pitcherSource",
    "line",
    "americanOdds",
    "allDataProbabilityPercent",
    "cachedStatsAdjustmentPercent",
    "weatherAdjustmentPercent",
    "oddsMovementAdjustmentPercent",
    "savantAdjustmentPercent",
    "finalProbabilityPercent",
    "sportsbookImpliedPercent",
    "finalEdgePercent",
    "confidence",
    "recommendation",
    "dataUsed",
    "missingData",
    "rawJson",
]

GRADE_FIELDS = [
    "predictionId",
    "gradedAt",
    "season",
    "date",
    "market",
    "player",
    "team",
    "opponent",
    "pitcher",
    "line",
    "americanOdds",
    "actualStat",
    "result",
    "profitUnits",
    "finalProbabilityPercent",
    "sportsbookImpliedPercent",
    "finalEdgePercent",
    "confidence",
    "recommendation",
    "gradeNote",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def normalize_name(value: Any) -> str:
    text = clean(value).lower()
    text = text.replace(".", "").replace(",", "")
    return " ".join(text.split())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def append_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def american_profit_units(american_odds: Any, result: str) -> float:
    odds = to_float(american_odds)

    if result == "push":
        return 0.0
    if result != "win":
        return -1.0

    if odds > 0:
        return round(odds / 100, 4)
    if odds < 0:
        return round(100 / abs(odds), 4)

    return 0.0


def prediction_id(payload: dict[str, Any]) -> str:
    base = "|".join([
        clean(payload.get("season")),
        clean(payload.get("date")),
        clean(payload.get("market")),
        normalize_name(payload.get("player")),
        clean(payload.get("team")).upper(),
        clean(payload.get("opponent")).upper(),
        clean(payload.get("line")),
        clean(payload.get("americanOdds")),
        clean(payload.get("savedAt")),
    ])

    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def prediction_file(season: int) -> Path:
    return PREDICTION_DIR / f"prediction_history_{season}.csv"


def grades_file(season: int) -> Path:
    return PREDICTION_DIR / f"prediction_grades_{season}.csv"


def serialize_list(value: Any) -> str:
    if isinstance(value, list):
        return " | ".join(clean(v) for v in value)
    return clean(value)


def save_prediction(card: dict[str, Any]) -> dict[str, Any]:
    season = int(to_float(card.get("season"), 2026))
    saved_at = now_iso()

    row = {
        "savedAt": saved_at,
        "season": season,
        "date": clean((card.get("allData") or {}).get("date") or card.get("date")),
        "market": clean(card.get("market")),
        "player": clean(card.get("player")),
        "team": clean(card.get("team")),
        "opponent": clean(card.get("opponent")),
        "pitcher": clean(card.get("pitcher")),
        "pitcherSource": clean(card.get("pitcherSource")),
        "line": clean(card.get("line")),
        "americanOdds": clean(card.get("americanOdds")),
        "allDataProbabilityPercent": clean(card.get("allDataProbabilityPercent")),
        "cachedStatsAdjustmentPercent": clean(card.get("cachedStatsAdjustmentPercent")),
        "weatherAdjustmentPercent": clean(card.get("weatherAdjustmentPercent")),
        "oddsMovementAdjustmentPercent": clean(card.get("oddsMovementAdjustmentPercent")),
        "savantAdjustmentPercent": clean(card.get("savantAdjustmentPercent")),
        "finalProbabilityPercent": clean(card.get("finalProbabilityPercent")),
        "sportsbookImpliedPercent": clean(card.get("sportsbookImpliedPercent")),
        "finalEdgePercent": clean(card.get("finalEdgePercent")),
        "confidence": clean(card.get("confidence")),
        "recommendation": clean(card.get("recommendation")),
        "dataUsed": serialize_list(card.get("dataUsed")),
        "missingData": serialize_list(card.get("missingData")),
        "rawJson": json.dumps(card, ensure_ascii=False),
    }

    row["predictionId"] = prediction_id(row)

    append_csv(prediction_file(season), PREDICTION_FIELDS, [row])

    status = {
        "season": season,
        "predictionId": row["predictionId"],
        "savedAt": saved_at,
        "predictionFile": str(prediction_file(season)),
        "message": "Prediction saved.",
    }
    write_json(PREDICTION_DIR / f"prediction_status_{season}.json", status)

    return status


def find_batter_row(season: int, date_label: str, player: str, team: str = "") -> dict[str, str]:
    target = normalize_name(player)
    team = clean(team).upper()

    rows = read_csv_rows(STATS_DIR / f"batter_game_logs_{season}.csv")
    for row in rows:
        if clean(row.get("date")) != clean(date_label):
            continue
        if normalize_name(row.get("player")) != target:
            continue
        if team and clean(row.get("team")).upper() and clean(row.get("team")).upper() != team:
            continue
        return row

    return {}


def find_pitcher_row(season: int, date_label: str, pitcher: str, team: str = "") -> dict[str, str]:
    target = normalize_name(pitcher)
    team = clean(team).upper()

    rows = read_csv_rows(STATS_DIR / f"pitcher_game_logs_{season}.csv")
    for row in rows:
        if clean(row.get("date")) != clean(date_label):
            continue
        if normalize_name(row.get("player")) != target:
            continue
        if team and clean(row.get("team")).upper() and clean(row.get("team")).upper() != team:
            continue
        return row

    return {}


def actual_stat_for_prediction(prediction: dict[str, str]) -> tuple[float | None, str]:
    season = int(to_float(prediction.get("season"), 2026))
    date_label = clean(prediction.get("date"))
    market = clean(prediction.get("market"))
    player = clean(prediction.get("player"))
    team = clean(prediction.get("team"))
    pitcher = clean(prediction.get("pitcher"))

    if market.startswith("batter"):
        row = find_batter_row(season, date_label, player, team)
        if not row:
            return None, "No batter game log found for this player/date."

        if market == "batter_hits":
            return to_float(row.get("hits")), "Graded from batter hits."
        if market == "batter_total_bases":
            return to_float(row.get("totalBases")), "Graded from batter total bases."
        if market == "batter_home_runs":
            return to_float(row.get("homeRuns")), "Graded from batter home runs."

        return None, f"Unsupported batter market: {market}"

    if market.startswith("pitcher"):
        pitcher_name = pitcher or player
        row = find_pitcher_row(season, date_label, pitcher_name, team)
        if not row:
            return None, "No pitcher game log found for this pitcher/date."

        if market == "pitcher_strikeouts":
            return to_float(row.get("strikeOuts")), "Graded from pitcher strikeouts."
        if market == "pitcher_hits_allowed":
            return to_float(row.get("hits")), "Graded from pitcher hits allowed."
        if market == "pitcher_earned_runs":
            return to_float(row.get("earnedRuns")), "Graded from pitcher earned runs."

        return None, f"Unsupported pitcher market: {market}"

    return None, f"Unsupported market: {market}"


def grade_over_result(actual: float, line: float) -> str:
    if actual > line:
        return "win"
    if actual == line:
        return "push"
    return "loss"


def grade_prediction_row(prediction: dict[str, str]) -> dict[str, Any]:
    season = int(to_float(prediction.get("season"), 2026))
    actual, note = actual_stat_for_prediction(prediction)

    if actual is None:
        result = "ungraded"
        profit = 0.0
    else:
        result = grade_over_result(actual, to_float(prediction.get("line")))
        profit = american_profit_units(prediction.get("americanOdds"), result)

    return {
        "predictionId": clean(prediction.get("predictionId")),
        "gradedAt": now_iso(),
        "season": season,
        "date": clean(prediction.get("date")),
        "market": clean(prediction.get("market")),
        "player": clean(prediction.get("player")),
        "team": clean(prediction.get("team")),
        "opponent": clean(prediction.get("opponent")),
        "pitcher": clean(prediction.get("pitcher")),
        "line": clean(prediction.get("line")),
        "americanOdds": clean(prediction.get("americanOdds")),
        "actualStat": "" if actual is None else actual,
        "result": result,
        "profitUnits": profit,
        "finalProbabilityPercent": clean(prediction.get("finalProbabilityPercent")),
        "sportsbookImpliedPercent": clean(prediction.get("sportsbookImpliedPercent")),
        "finalEdgePercent": clean(prediction.get("finalEdgePercent")),
        "confidence": clean(prediction.get("confidence")),
        "recommendation": clean(prediction.get("recommendation")),
        "gradeNote": note,
    }


def grade_predictions(season: int = 2026) -> dict[str, Any]:
    predictions = read_csv_rows(prediction_file(season))
    grades = [grade_prediction_row(row) for row in predictions]

    write_csv(grades_file(season), GRADE_FIELDS, grades)

    graded = [row for row in grades if row.get("result") in {"win", "loss", "push"}]
    wins = sum(1 for row in graded if row.get("result") == "win")
    losses = sum(1 for row in graded if row.get("result") == "loss")
    pushes = sum(1 for row in graded if row.get("result") == "push")
    profit = round(sum(to_float(row.get("profitUnits")) for row in graded), 4)

    status = {
        "season": season,
        "predictions": len(predictions),
        "graded": len(graded),
        "ungraded": len(predictions) - len(graded),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "profitUnits": profit,
        "winRate": round((wins / (wins + losses)) * 100, 2) if (wins + losses) else 0,
        "predictionFile": str(prediction_file(season)),
        "gradesFile": str(grades_file(season)),
        "updatedAt": now_iso(),
    }

    write_json(PREDICTION_DIR / f"prediction_grade_status_{season}.json", status)
    return status


def status(season: int = 2026) -> dict[str, Any]:
    predictions = read_csv_rows(prediction_file(season))
    grades = read_csv_rows(grades_file(season))

    return {
        "season": season,
        "predictions": len(predictions),
        "grades": len(grades),
        "predictionFile": str(prediction_file(season)),
        "gradesFile": str(grades_file(season)),
        "updatedAt": now_iso(),
    }



def summarize_group(rows: list[dict[str, str]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = {}

    for row in rows:
        value = clean(row.get(key)) or "Unknown"
        grouped.setdefault(value, []).append(row)

    output = []
    for value, items in grouped.items():
        graded = [row for row in items if row.get("result") in {"win", "loss", "push"}]
        wins = sum(1 for row in graded if row.get("result") == "win")
        losses = sum(1 for row in graded if row.get("result") == "loss")
        pushes = sum(1 for row in graded if row.get("result") == "push")
        profit = round(sum(to_float(row.get("profitUnits")) for row in graded), 4)
        risked = wins + losses

        output.append({
            key: value,
            "picks": len(items),
            "graded": len(graded),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "winRate": round((wins / risked) * 100, 2) if risked else 0,
            "profitUnits": profit,
            "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        })

    return sorted(output, key=lambda row: to_float(row.get("profitUnits")), reverse=True)


def prediction_dashboard(
    season: int = 2026,
    market: str = "",
    confidence: str = "",
    recommendation: str = "",
    date: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    grades = read_csv_rows(grades_file(season))

    if market:
        grades = [row for row in grades if clean(row.get("market")) == clean(market)]

    if confidence:
        grades = [row for row in grades if clean(row.get("confidence")) == clean(confidence)]

    if recommendation:
        grades = [row for row in grades if clean(row.get("recommendation")) == clean(recommendation)]

    if date:
        grades = [row for row in grades if clean(row.get("date")) == clean(date)]

    graded = [row for row in grades if row.get("result") in {"win", "loss", "push"}]
    wins = sum(1 for row in graded if row.get("result") == "win")
    losses = sum(1 for row in graded if row.get("result") == "loss")
    pushes = sum(1 for row in graded if row.get("result") == "push")
    ungraded = len(grades) - len(graded)
    profit = round(sum(to_float(row.get("profitUnits")) for row in graded), 4)
    risked = wins + losses

    recent = sorted(grades, key=lambda row: clean(row.get("gradedAt")), reverse=True)[:limit]

    return {
        "season": season,
        "filters": {
            "market": market,
            "confidence": confidence,
            "recommendation": recommendation,
            "date": date,
            "limit": limit,
        },
        "summary": {
            "picks": len(grades),
            "graded": len(graded),
            "ungraded": ungraded,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "winRate": round((wins / risked) * 100, 2) if risked else 0,
            "profitUnits": profit,
            "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        },
        "byMarket": summarize_group(grades, "market"),
        "byConfidence": summarize_group(grades, "confidence"),
        "byRecommendation": summarize_group(grades, "recommendation"),
        "recent": recent,
        "gradesFile": str(grades_file(season)),
        "updatedAt": now_iso(),
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Save and grade prediction history.")
    sub = parser.add_subparsers(dest="command", required=True)

    grade = sub.add_parser("grade")
    grade.add_argument("--season", type=int, default=2026)

    stat = sub.add_parser("status")
    stat.add_argument("--season", type=int, default=2026)

    args = parser.parse_args()

    if args.command == "grade":
        print(json.dumps(grade_predictions(args.season), indent=2))
    elif args.command == "status":
        print(json.dumps(status(args.season), indent=2))


if __name__ == "__main__":
    main()
