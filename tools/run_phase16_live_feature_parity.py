from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase16_common import DEFAULT_MARKETS, ROOT


def run_step(args: list[str]) -> dict[str, object]:
    completed = subprocess.run([sys.executable, *args], cwd=str(ROOT), text=True, capture_output=True)
    return {
        "command": [sys.executable, *args],
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "status": "ok" if completed.returncode == 0 else "error",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 16 live feature parity workflow.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--markets", nargs="+", default=["batter_hits", "batter_total_bases"])
    args = parser.parse_args()

    market_args = ["--markets", *args.markets]
    steps = [
        ["tools/phase16_feature_contract.py", *market_args, "--write"],
        ["tools/phase16_enrich_live_playerboard.py", "--date", args.date, "--season", str(args.season), *market_args],
        ["tools/phase16_live_feature_audit.py", *market_args, "--season", str(args.season), "--date", args.date, "--write"],
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
