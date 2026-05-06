from __future__ import annotations

"""Export ML-ready Playerboard training data.

Reads:
- data/backtests/playerboard_backtest_2026.csv
- data/audit/model_audit_2026.csv, if present

Writes:
- data/ml/playerboard_training_2026.csv
- data/ml/playerboard_training_summary_2026.json

Purpose:
- Produce one clean ML-ready table with pre-game features and post-game labels.
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BACKTEST_DIR = ROOT / "data" / "backtests"
AUDIT_DIR = ROOT / "data" / "audit"
ML_DIR = ROOT / "data" / "ml"

TRAINING_FIELDS = [
    "season",
    "snapshotAt",
    "date",
    "market",
    "marketGroup",
    "player",
    "team",
    "opponent",
    "pitcher",
    "line",
    "americanOdds",
    "sportsbookImpliedPercent",
    "finalProbabilityPercent",
    "finalEdgePercent",
    "edgeBucket",
    "probabilityBucket",
    "confidence",
    "recommendation",
    "weatherAdjustmentPercent",
    "savantAdjustmentPercent",
    "oddsMovementAdjustmentPercent",
    "hasWeatherBoost",
    "hasSavantBoost",
    "hasOddsMovementBoost",
    "missingData",
    "actualStat",
    "result",
    "overHit",
    "push",
    "profitUnits",
    "calculatedImpliedPercent",
    "calculatedEdgePercent",
    "edgeDelta",
    "mathStatus",
    "warnings",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm(value: Any) -> str:
    return " ".join(clean(value).lower().replace(".", "").replace(",", "").split())


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


def market_group(market: Any) -> str:
    text = clean(market)
    if text.startswith("batter_"):
        return "batter"
    if text.startswith("pitcher_"):
        return "pitcher"
    return "other"


def edge_bucket(edge: Any) -> str:
    value = to_float(edge)
    if value < 0:
        return "<0%"
    if value < 2:
        return "0-2%"
    if value < 4:
        return "2-4%"
    if value < 6:
        return "4-6%"
    if value < 8:
        return "6-8%"
    return "8%+"


def probability_bucket(probability: Any) -> str:
    value = to_float(probability)
    if value < 45:
        return "<45%"
    if value < 50:
        return "45-50%"
    if value < 55:
        return "50-55%"
    if value < 60:
        return "55-60%"
    if value < 65:
        return "60-65%"
    if value < 70:
        return "65-70%"
    return "70%+"


def label_over_hit(result: Any) -> str:
    text = clean(result).lower()
    if text == "win":
        return "1"
    if text == "loss":
        return "0"
    return ""


def label_push(result: Any) -> str:
    return "1" if clean(result).lower() == "push" else "0"


def bool_flag(value: Any) -> str:
    return "1" if to_float(value) > 0 else "0"


def row_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        clean(row.get("date"))[:10],
        clean(row.get("market")),
        norm(row.get("player")),
        clean(row.get("team")).upper(),
        clean(row.get("opponent")).upper(),
        clean(row.get("pitcher")).lower(),
        clean(row.get("line")),
        clean(row.get("americanOdds")),
    )


def audit_lookup(season: int) -> dict[tuple[str, ...], dict[str, str]]:
    path = AUDIT_DIR / f"model_audit_{season}.csv"
    lookup: dict[tuple[str, ...], dict[str, str]] = {}

    for row in read_csv_rows(path):
        key = row_key(row)
        lookup[key] = row

    return lookup


def export_playerboard_training(season: int = 2026) -> dict[str, Any]:
    backtest_path = BACKTEST_DIR / f"playerboard_backtest_{season}.csv"
    audit_rows = audit_lookup(season)
    source_rows = read_csv_rows(backtest_path)

    training_rows = []
    seen = set()

    for row in source_rows:
        key = row_key(row)
        if key in seen:
            continue
        seen.add(key)

        audit = audit_rows.get(key, {})

        result = clean(row.get("result")).lower()
        is_graded = result in {"win", "loss", "push"}

        training_rows.append({
            "season": clean(row.get("season")) or season,
            "snapshotAt": clean(row.get("snapshotAt")),
            "date": clean(row.get("date"))[:10],
            "market": clean(row.get("market")),
            "marketGroup": market_group(row.get("market")),
            "player": clean(row.get("player")),
            "team": clean(row.get("team")),
            "opponent": clean(row.get("opponent")),
            "pitcher": clean(row.get("pitcher")),
            "line": clean(row.get("line")),
            "americanOdds": clean(row.get("americanOdds")),
            "sportsbookImpliedPercent": clean(row.get("sportsbookImpliedPercent")),
            "finalProbabilityPercent": clean(row.get("finalProbabilityPercent")),
            "finalEdgePercent": clean(row.get("finalEdgePercent")),
            "edgeBucket": edge_bucket(row.get("finalEdgePercent")),
            "probabilityBucket": probability_bucket(row.get("finalProbabilityPercent")),
            "confidence": clean(row.get("confidence")),
            "recommendation": clean(row.get("recommendation")),
            "weatherAdjustmentPercent": clean(row.get("weatherAdjustmentPercent")),
            "savantAdjustmentPercent": clean(row.get("savantAdjustmentPercent")),
            "oddsMovementAdjustmentPercent": clean(row.get("oddsMovementAdjustmentPercent")),
            "hasWeatherBoost": bool_flag(row.get("weatherAdjustmentPercent")),
            "hasSavantBoost": bool_flag(row.get("savantAdjustmentPercent")),
            "hasOddsMovementBoost": bool_flag(row.get("oddsMovementAdjustmentPercent")),
            "missingData": clean(row.get("missingData")),
            "actualStat": clean(row.get("actualStat")),
            "result": result if is_graded else "ungraded",
            "overHit": label_over_hit(result),
            "push": label_push(result),
            "profitUnits": clean(row.get("profitUnits")),
            "calculatedImpliedPercent": clean(audit.get("calculatedImpliedPercent")),
            "calculatedEdgePercent": clean(audit.get("calculatedEdgePercent")),
            "edgeDelta": clean(audit.get("edgeDelta")),
            "mathStatus": clean(audit.get("mathStatus")),
            "warnings": clean(audit.get("warnings")),
        })

    output_path = ML_DIR / f"playerboard_training_{season}.csv"
    summary_path = ML_DIR / f"playerboard_training_summary_{season}.json"

    write_csv(output_path, TRAINING_FIELDS, training_rows)

    graded = [r for r in training_rows if r.get("result") in {"win", "loss", "push"}]
    wins = sum(1 for r in graded if r.get("result") == "win")
    losses = sum(1 for r in graded if r.get("result") == "loss")
    pushes = sum(1 for r in graded if r.get("result") == "push")
    risked = wins + losses
    profit = round(sum(to_float(r.get("profitUnits")) for r in graded), 4)

    by_market: dict[str, int] = {}
    by_result: dict[str, int] = {}
    by_edge_bucket: dict[str, int] = {}

    for row in training_rows:
        by_market[row["market"]] = by_market.get(row["market"], 0) + 1
        by_result[row["result"]] = by_result.get(row["result"], 0) + 1
        by_edge_bucket[row["edgeBucket"]] = by_edge_bucket.get(row["edgeBucket"], 0) + 1

    summary = {
        "season": season,
        "updatedAt": now_iso(),
        "source": str(backtest_path),
        "trainingFile": str(output_path),
        "summaryFile": str(summary_path),
        "rows": len(training_rows),
        "graded": len(graded),
        "ungraded": len(training_rows) - len(graded),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "profitUnits": profit,
        "winRate": round((wins / risked) * 100, 2) if risked else 0,
        "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        "byMarket": dict(sorted(by_market.items())),
        "byResult": dict(sorted(by_result.items())),
        "byEdgeBucket": dict(sorted(by_edge_bucket.items())),
    }

    write_json(summary_path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ML-ready Playerboard training data.")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    print(json.dumps(export_playerboard_training(args.season), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
