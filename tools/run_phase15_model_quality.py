from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase15_common import DEFAULT_MARKETS, ROOT


def run_step(args: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    return {
        "command": [sys.executable, *args],
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "status": "ok" if completed.returncode == 0 else "error",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 15 model-quality workflow.")
    parser.add_argument("--markets", nargs="+", default=["batter_hits", "batter_total_bases"])
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--date", default=None)
    parser.add_argument("--holdout-fraction", type=float, default=0.25)
    args = parser.parse_args()

    market_args = ["--markets", *args.markets]
    steps: list[list[str]] = [
        ["tools/phase15_feature_audit.py", *market_args, "--season", str(args.season), *( ["--date", args.date] if args.date else [] ), "--write"],
        ["tools/phase15_build_quality_dataset.py", *market_args, "--write"],
        ["tools/phase15_backtest_walk_forward.py", *market_args, "--holdout-fraction", str(args.holdout_fraction), "--update-registry"],
        ["tools/phase15_calibration_report.py", *market_args, "--write"],
        ["tools/validate_model_readiness.py", "--json"],
    ]
    results = []
    for step in steps:
        result = run_step(step)
        results.append(result)
        if result["returncode"] != 0:
            break
    print(json.dumps({"status": "ok" if all(item["returncode"] == 0 for item in results) else "error", "steps": results}, indent=2))


if __name__ == "__main__":
    main()
