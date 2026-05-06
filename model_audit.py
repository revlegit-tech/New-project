from __future__ import annotations

"""Model math/backtest audit.

Reads:
- data/backtests/playerboard_backtest_2026.csv
- data/predictions/prediction_grades_2026.csv, if present

Writes:
- data/audit/model_audit_2026.json
- data/audit/model_audit_2026.csv

Purpose:
- Confirm implied probability, edge, and profit math.
- Surface suspicious odds/probability rows.
- Show calibration/ROI by bucket.
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BACKTEST_DIR = ROOT / "data" / "backtests"
PREDICTIONS_DIR = ROOT / "data" / "predictions"
AUDIT_DIR = ROOT / "data" / "audit"

AUDIT_FIELDS = [
    "source",
    "date",
    "market",
    "player",
    "team",
    "opponent",
    "pitcher",
    "line",
    "americanOdds",
    "modelProbabilityPercent",
    "storedImpliedPercent",
    "calculatedImpliedPercent",
    "storedEdgePercent",
    "calculatedEdgePercent",
    "edgeDelta",
    "actualStat",
    "result",
    "storedProfitUnits",
    "calculatedProfitUnits",
    "profitDelta",
    "confidence",
    "recommendation",
    "mathStatus",
    "warnings",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def implied_probability_percent(american_odds: Any) -> float:
    odds = to_float(american_odds)
    if odds < 0:
        return round(abs(odds) / (abs(odds) + 100) * 100, 4)
    if odds > 0:
        return round(100 / (odds + 100) * 100, 4)
    return 0.0


def profit_units(american_odds: Any, result: str) -> float:
    odds = to_float(american_odds)
    result = clean(result).lower()

    if result == "push":
        return 0.0
    if result == "loss":
        return -1.0
    if result != "win":
        return 0.0

    if odds > 0:
        return round(odds / 100, 4)
    if odds < 0:
        return round(100 / abs(odds), 4)

    return 0.0


def probability_bucket(probability_percent: Any) -> str:
    p = to_float(probability_percent)

    if p < 45:
        return "<45%"
    if p < 50:
        return "45-50%"
    if p < 55:
        return "50-55%"
    if p < 60:
        return "55-60%"
    if p < 65:
        return "60-65%"
    if p < 70:
        return "65-70%"
    return "70%+"


def edge_bucket(edge_percent: Any) -> str:
    e = to_float(edge_percent)

    if e < 0:
        return "<0%"
    if e < 2:
        return "0-2%"
    if e < 4:
        return "2-4%"
    if e < 6:
        return "4-6%"
    if e < 8:
        return "6-8%"
    return "8%+"


def odds_suspicion(market: str, line: Any, odds: Any) -> list[str]:
    market = clean(market)
    line_value = to_float(line)
    odds_value = to_float(odds)
    abs_odds = abs(odds_value)
    warnings = []

    if odds_value == 0:
        warnings.append("missing_or_zero_odds")

    if market != "batter_home_runs" and abs_odds > 2000:
        warnings.append("extreme_non_hr_odds")

    if market == "batter_hits" and line_value <= 0.5 and odds_value > 1000:
        warnings.append("suspicious_batter_hits_odds")

    if market == "batter_total_bases" and line_value <= 1.5 and odds_value > 1500:
        warnings.append("suspicious_total_bases_odds")

    if market.startswith("pitcher_") and abs_odds > 1500:
        warnings.append("suspicious_pitcher_prop_odds")

    if line_value < 0:
        warnings.append("negative_line")

    return warnings


def normalize_backtest_row(row: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "source": source,
        "date": clean(row.get("date")),
        "market": clean(row.get("market")),
        "player": clean(row.get("player")),
        "team": clean(row.get("team")),
        "opponent": clean(row.get("opponent")),
        "pitcher": clean(row.get("pitcher")),
        "line": clean(row.get("line")),
        "americanOdds": clean(row.get("americanOdds")),
        "modelProbabilityPercent": clean(row.get("finalProbabilityPercent")),
        "storedImpliedPercent": clean(row.get("sportsbookImpliedPercent")),
        "storedEdgePercent": clean(row.get("finalEdgePercent")),
        "actualStat": clean(row.get("actualStat")),
        "result": clean(row.get("result")),
        "storedProfitUnits": clean(row.get("profitUnits")),
        "confidence": clean(row.get("confidence")),
        "recommendation": clean(row.get("recommendation")),
    }


def audit_row(row: dict[str, Any]) -> dict[str, Any]:
    model_prob = to_float(row.get("modelProbabilityPercent"))
    stored_implied = to_float(row.get("storedImpliedPercent"))
    calculated_implied = implied_probability_percent(row.get("americanOdds"))
    stored_edge = to_float(row.get("storedEdgePercent"))
    calculated_edge = round(model_prob - calculated_implied, 4)

    stored_profit = to_float(row.get("storedProfitUnits"))
    calculated_profit = profit_units(row.get("americanOdds"), row.get("result"))

    edge_delta = round(stored_edge - calculated_edge, 4)
    profit_delta = round(stored_profit - calculated_profit, 4)

    warnings = []

    if model_prob < 0 or model_prob > 100:
        warnings.append("model_probability_out_of_bounds")

    if stored_implied and abs(stored_implied - calculated_implied) > 0.05:
        warnings.append("implied_probability_mismatch")

    if abs(edge_delta) > 0.1:
        warnings.append("edge_mismatch")

    if clean(row.get("result")).lower() in {"win", "loss", "push"} and abs(profit_delta) > 0.01:
        warnings.append("profit_mismatch")

    warnings.extend(odds_suspicion(row.get("market"), row.get("line"), row.get("americanOdds")))

    return {
        **row,
        "calculatedImpliedPercent": calculated_implied,
        "calculatedEdgePercent": calculated_edge,
        "edgeDelta": edge_delta,
        "calculatedProfitUnits": calculated_profit,
        "profitDelta": profit_delta,
        "mathStatus": "ok" if not warnings else "warning",
        "warnings": " | ".join(sorted(set(warnings))),
    }


def summarize_group(rows: list[dict[str, Any]], bucket: str, key_fn) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        key = clean(key_fn(row)) or "Unknown"
        groups.setdefault(key, []).append(row)

    output = []

    for name, items in groups.items():
        graded = [r for r in items if clean(r.get("result")).lower() in {"win", "loss", "push"}]
        wins = sum(1 for r in graded if clean(r.get("result")).lower() == "win")
        losses = sum(1 for r in graded if clean(r.get("result")).lower() == "loss")
        pushes = sum(1 for r in graded if clean(r.get("result")).lower() == "push")
        risked = wins + losses
        profit = round(sum(to_float(r.get("calculatedProfitUnits")) for r in graded), 4)

        output.append({
            "bucket": bucket,
            "name": name,
            "rows": len(items),
            "graded": len(graded),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "profitUnits": profit,
            "winRate": round((wins / risked) * 100, 2) if risked else 0,
            "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        })

    return sorted(output, key=lambda x: to_float(x.get("profitUnits")), reverse=True)


def audit_model_math(season: int = 2026) -> dict[str, Any]:
    rows = []

    board_path = BACKTEST_DIR / f"playerboard_backtest_{season}.csv"
    for row in read_csv_rows(board_path):
        rows.append(normalize_backtest_row(row, "playerboard_backtest"))

    grade_path = PREDICTIONS_DIR / f"prediction_grades_{season}.csv"
    for row in read_csv_rows(grade_path):
        rows.append(normalize_backtest_row(row, "saved_predictions"))

    audited = [audit_row(row) for row in rows]

    warnings = [row for row in audited if row.get("mathStatus") == "warning"]
    graded = [row for row in audited if clean(row.get("result")).lower() in {"win", "loss", "push"}]
    wins = sum(1 for row in graded if clean(row.get("result")).lower() == "win")
    losses = sum(1 for row in graded if clean(row.get("result")).lower() == "loss")
    pushes = sum(1 for row in graded if clean(row.get("result")).lower() == "push")
    risked = wins + losses
    profit = round(sum(to_float(row.get("calculatedProfitUnits")) for row in graded), 4)

    breakdowns = []
    breakdowns.extend(summarize_group(audited, "source", lambda r: r.get("source")))
    breakdowns.extend(summarize_group(audited, "market", lambda r: r.get("market")))
    breakdowns.extend(summarize_group(audited, "probabilityBucket", lambda r: probability_bucket(r.get("modelProbabilityPercent"))))
    breakdowns.extend(summarize_group(audited, "edgeBucket", lambda r: edge_bucket(r.get("storedEdgePercent"))))
    breakdowns.extend(summarize_group(audited, "confidence", lambda r: r.get("confidence")))
    breakdowns.extend(summarize_group(audited, "recommendation", lambda r: r.get("recommendation")))

    csv_path = AUDIT_DIR / f"model_audit_{season}.csv"
    json_path = AUDIT_DIR / f"model_audit_{season}.json"

    write_csv(csv_path, AUDIT_FIELDS, audited)

    summary = {
        "season": season,
        "updatedAt": now_iso(),
        "rows": len(audited),
        "graded": len(graded),
        "ungraded": len(audited) - len(graded),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "profitUnits": profit,
        "winRate": round((wins / risked) * 100, 2) if risked else 0,
        "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        "warningRows": len(warnings),
        "auditCsv": str(csv_path),
        "auditJson": str(json_path),
        "topWarnings": warnings[:25],
        "breakdowns": breakdowns,
    }

    write_json(json_path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit model math and backtest calibration.")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    print(json.dumps(audit_model_math(args.season), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
