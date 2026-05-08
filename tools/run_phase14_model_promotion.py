from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORTS))

from tools.phase14_common import DEFAULT_MARKETS, ROOT


def run_step(args: list[str], *, skip: bool = False) -> dict:
    if skip:
        return {"command": args, "status": "skipped"}
    completed = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)
    return {
        "command": [sys.executable, *args],
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "status": "ok" if completed.returncode == 0 else "failed",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 14 controlled model promotion workflow.")
    parser.add_argument("--markets", nargs="*", default=["batter_hits", "batter_total_bases"])
    parser.add_argument("--skip-expand", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--promote", action="store_true", help="Write production promotion if gates pass. Without this, promotion is a dry run.")
    args = parser.parse_args()

    markets = args.markets or DEFAULT_MARKETS
    steps = [
        run_step(["tools/phase14_market_gap_report.py", "--markets", *markets, "--json"]),
        run_step(["tools/phase14_expand_training_data.py", "--markets", *markets, "--write"], skip=args.skip_expand),
        run_step(["tools/train_market_models.py", "--markets", *markets, "--calibrate"], skip=args.skip_train),
        run_step(["tools/phase14_backtest_market_artifacts.py", "--markets", *markets, "--update-registry"], skip=args.skip_backtest),
        run_step(["tools/phase14_promote_market_models.py", "--markets", *markets, *( ["--write"] if args.promote else [] )]),
        run_step(["tools/validate_model_readiness.py", "--json"]),
    ]
    status = "ok" if all(step.get("status") in {"ok", "skipped"} for step in steps) else "failed"
    print(json.dumps({"status": status, "markets": markets, "steps": steps}, indent=2))
    if status != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
