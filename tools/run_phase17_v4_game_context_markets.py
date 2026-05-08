#!/usr/bin/env python3
"""Run the Phase 17 v4 game-context market workflow.

This wrapper keeps the existing providers flexible:
- If --refresh-provider is supplied, it first calls run_phase17_context_from_apis.py
  with --line-source propline, the_odds_api, or auto.
- It then builds canonical game_context/game_context_markets CSVs and denormalizes
  the result onto Playerboard for UI speed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def run_step(command: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(command, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
        "status": "ok" if proc.returncode == 0 else "error",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 17 v4 canonical game-context market workflow.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--markets", nargs="*", default=[])
    parser.add_argument("--line-source", choices=["propline", "the_odds_api", "auto"], default="propline")
    parser.add_argument("--refresh-provider", action="store_true", help="Fetch schedule/weather/game-line provider payload before building context markets.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    steps = []
    if args.refresh_provider:
        cmd = [sys.executable, "tools/run_phase17_context_from_apis.py", "--date", args.date, "--season", str(args.season), "--line-source", args.line_source]
        if args.markets:
            cmd += ["--markets", *args.markets]
        steps.append(run_step(cmd))

    cmd = [sys.executable, "tools/phase17_game_context_markets.py", "--date", args.date, "--season", str(args.season)]
    if args.markets:
        cmd += ["--markets", *args.markets]
    if args.dry_run:
        cmd.append("--dry-run")
    steps.append(run_step(cmd))

    if not args.dry_run:
        # Existing audits remain useful, but failures here should not hide the v4 artifact result.
        for script in ("tools/phase17_game_context_audit.py", "tools/phase16_live_feature_audit.py"):
            path = ROOT / script
            if path.exists():
                cmd = [sys.executable, script, "--date", args.date, "--season", str(args.season), "--write"]
                if args.markets:
                    cmd += ["--markets", *args.markets]
                steps.append(run_step(cmd))

    status = "ok" if all(step["returncode"] == 0 for step in steps[:2 if args.refresh_provider else 1]) else "error"
    print(json.dumps({"status": status, "date": args.date, "season": args.season, "markets": args.markets, "steps": steps}, indent=2))


if __name__ == "__main__":
    main()
