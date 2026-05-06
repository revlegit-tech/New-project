from __future__ import annotations

"""Compact model performance summary.

Reads:
- data/ml/playerboard_training_2026.csv
- data/audit/model_audit_2026.json
- data/backtests/playerboard_backtest_summary_2026.json

Used by:
- /api/model/performance?season=2026
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ML_DIR = ROOT / "data" / "ml"
AUDIT_DIR = ROOT / "data" / "audit"
BACKTEST_DIR = ROOT / "data" / "backtests"


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default


def summarize_group(rows: list[dict[str, Any]], key: str, limit: int = 8) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        name = clean(row.get(key)) or "Unknown"
        groups.setdefault(name, []).append(row)

    out = []
    for name, items in groups.items():
        graded = [r for r in items if clean(r.get("result")).lower() in {"win", "loss", "push"}]
        wins = sum(1 for r in graded if clean(r.get("result")).lower() == "win")
        losses = sum(1 for r in graded if clean(r.get("result")).lower() == "loss")
        pushes = sum(1 for r in graded if clean(r.get("result")).lower() == "push")
        risked = wins + losses
        profit = round(sum(to_float(r.get("profitUnits")) for r in graded), 4)

        out.append({
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

    return sorted(out, key=lambda r: (to_float(r.get("profitUnits")), to_float(r.get("roiPercent"))), reverse=True)[:limit]


def warning_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}

    for row in rows:
        warnings = clean(row.get("warnings"))
        if not warnings:
            continue

        for item in warnings.split("|"):
            warning = clean(item)
            if not warning:
                continue
            counts[warning] = counts.get(warning, 0) + 1

    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def performance_summary(season: int = 2026) -> dict[str, Any]:
    training_path = ML_DIR / f"playerboard_training_{season}.csv"
    audit_path = AUDIT_DIR / f"model_audit_{season}.json"
    backtest_summary_path = BACKTEST_DIR / f"playerboard_backtest_summary_{season}.json"

    rows = read_csv_rows(training_path)
    audit = read_json(audit_path, {})
    backtest = read_json(backtest_summary_path, {})

    graded = [r for r in rows if clean(r.get("result")).lower() in {"win", "loss", "push"}]
    wins = sum(1 for r in graded if clean(r.get("result")).lower() == "win")
    losses = sum(1 for r in graded if clean(r.get("result")).lower() == "loss")
    pushes = sum(1 for r in graded if clean(r.get("result")).lower() == "push")
    risked = wins + losses
    profit = round(sum(to_float(r.get("profitUnits")) for r in graded), 4)

    warning_rows = [r for r in rows if clean(r.get("mathStatus")).lower() == "warning" or clean(r.get("warnings"))]

    return {
        "season": season,
        "trainingFile": str(training_path),
        "auditFile": str(audit_path),
        "backtestSummaryFile": str(backtest_summary_path),
        "rows": len(rows),
        "graded": len(graded),
        "ungraded": len(rows) - len(graded),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "profitUnits": profit,
        "winRate": round((wins / risked) * 100, 2) if risked else 0,
        "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        "warningRows": len(warning_rows),
        "warningRate": round((len(warning_rows) / len(rows)) * 100, 2) if rows else 0,
        "warningCounts": warning_counts(rows),
        "bestMarkets": summarize_group(rows, "market"),
        "bestEdgeBuckets": summarize_group(rows, "edgeBucket"),
        "bestProbabilityBuckets": summarize_group(rows, "probabilityBucket"),
        "bestConfidence": summarize_group(rows, "confidence"),
        "bestRecommendations": summarize_group(rows, "recommendation"),
        "auditSummary": {
            "rows": audit.get("rows", 0),
            "warningRows": audit.get("warningRows", 0),
            "roiPercent": audit.get("roiPercent", 0),
            "winRate": audit.get("winRate", 0),
        },
        "backtestSummary": {
            "props": backtest.get("props", 0),
            "graded": backtest.get("graded", 0),
            "profitUnits": backtest.get("profitUnits", 0),
            "roiPercent": backtest.get("roiPercent", 0),
            "winRate": backtest.get("winRate", 0),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Show compact model performance summary.")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    print(json.dumps(performance_summary(args.season), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
