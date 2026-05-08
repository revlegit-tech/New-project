from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]


def run_step(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, text=True, capture_output=True)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-20000:],
        "stderr": completed.stderr[-8000:],
        "status": "ok" if completed.returncode == 0 else "error",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 17 game-context enrichment and audit.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-readiness", action="store_true")
    args = parser.parse_args()

    python = sys.executable
    market_args = ["--markets", *args.markets]
    steps: list[dict[str, object]] = []

    enrich_cmd = [
        python,
        "tools/phase17_enrich_game_context.py",
        "--date",
        args.date,
        "--season",
        str(args.season),
        *market_args,
    ]
    if args.dry_run:
        enrich_cmd.append("--dry-run")
    steps.append(run_step(enrich_cmd))

    steps.append(
        run_step(
            [
                python,
                "tools/phase17_game_context_audit.py",
                "--date",
                args.date,
                "--season",
                str(args.season),
                *market_args,
                "--write",
            ]
        )
    )

    if not args.skip_readiness and Path("tools/validate_model_readiness.py").exists():
        steps.append(run_step([python, "tools/validate_model_readiness.py", "--json"]))

    status = "ok" if all(step["returncode"] == 0 for step in steps) else "error"
    print(json.dumps({"status": status, "date": args.date, "season": args.season, "markets": args.markets, "steps": steps}, indent=2))
    if status != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
