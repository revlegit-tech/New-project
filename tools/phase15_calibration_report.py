from __future__ import annotations

import argparse
import json
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase15_common import DEFAULT_MARKETS, atomic_write_json, phase15_backtest_path, phase15_calibration_path, read_json


def calibration_for_market(market: str, buckets: int = 10) -> dict[str, Any]:
    report = read_json(phase15_backtest_path(market), default={}) or {}
    predictions = report.get("predictions") or []
    if not predictions:
        return {"market": market, "status": "missing_predictions", "source": str(phase15_backtest_path(market))}
    bins = []
    for index in range(buckets):
        lower = index / buckets
        upper = (index + 1) / buckets
        rows = [
            row
            for row in predictions
            if lower <= float(row.get("probability", 0)) < upper or (index == buckets - 1 and float(row.get("probability", 0)) == 1.0)
        ]
        if rows:
            avg_prob = sum(float(row["probability"]) for row in rows) / len(rows)
            actual = sum(int(row["actual"]) for row in rows) / len(rows)
        else:
            avg_prob = 0.0
            actual = 0.0
        bins.append(
            {
                "bucket": f"{int(lower * 100)}-{int(upper * 100)}%",
                "lower": round(lower, 2),
                "upper": round(upper, 2),
                "rows": len(rows),
                "averageProbability": round(avg_prob, 4),
                "actualRate": round(actual, 4),
                "calibrationGap": round(abs(avg_prob - actual), 4) if rows else None,
            }
        )
    non_empty = [row for row in bins if row["rows"]]
    weighted_gap = 0.0
    total_rows = sum(row["rows"] for row in non_empty)
    if total_rows:
        weighted_gap = sum((row["calibrationGap"] or 0) * row["rows"] for row in non_empty) / total_rows
    return {
        "market": market,
        "status": "ok",
        "source": str(phase15_backtest_path(market)),
        "rows": len(predictions),
        "weightedCalibrationGap": round(weighted_gap, 4),
        "bins": bins,
        "out": str(phase15_calibration_path(market)),
    }


def run(markets: list[str], write: bool = False, buckets: int = 10) -> dict[str, Any]:
    results = [calibration_for_market(market, buckets=buckets) for market in markets]
    if write:
        for result in results:
            if result.get("status") == "ok":
                atomic_write_json(phase15_calibration_path(result["market"]), result)
    return {"status": "ok", "dryRun": not write, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Phase 15 calibration reports.")
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    parser.add_argument("--buckets", type=int, default=10)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.markets, write=args.write, buckets=args.buckets), indent=2))


if __name__ == "__main__":
    main()
