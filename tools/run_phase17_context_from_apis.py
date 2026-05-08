#!/usr/bin/env python3
"""One-command Phase 17 API context refresh wrapper."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_step(args: list[str]) -> dict:
    proc = subprocess.run(args, cwd=str(PROJECT_ROOT), text=True, capture_output=True)  # noqa: S603
    payload = {
        "command": args,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-6000:],
        "status": "ok" if proc.returncode == 0 else "error",
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 17 API context enrichment and audits.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--markets", nargs="*", default=["batter_hits", "batter_total_bases"])
    parser.add_argument("--skip-weather", action="store_true")
    parser.add_argument("--skip-odds", action="store_true", help="Legacy alias for --line-source none")
    parser.add_argument("--line-source", choices=["propline", "the_odds_api", "none"], default="propline")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    steps = []
    fetch_cmd = [
        sys.executable,
        "tools/fetch_phase17_context_from_apis.py",
        "--date",
        args.date,
        "--season",
        str(args.season),
        "--markets",
        *args.markets,
    ]
    if args.skip_weather:
        fetch_cmd.append("--skip-weather")
    if args.skip_odds:
        fetch_cmd.append("--skip-odds")
    else:
        fetch_cmd.extend(["--line-source", args.line_source])
    if args.dry_run:
        fetch_cmd.append("--dry-run")
    steps.append(run_step(fetch_cmd))

    # If the Phase 17 audit script exists, run it after enrichment.
    audit_path = PROJECT_ROOT / "tools" / "phase17_game_context_audit.py"
    if audit_path.exists() and not args.dry_run:
        steps.append(
            run_step(
                [
                    sys.executable,
                    "tools/phase17_game_context_audit.py",
                    "--date",
                    args.date,
                    "--season",
                    str(args.season),
                    "--markets",
                    *args.markets,
                    "--write",
                ]
            )
        )

    # Phase 16 live-feature audit remains useful to confirm model field coverage.
    live_audit_path = PROJECT_ROOT / "tools" / "phase16_live_feature_audit.py"
    if live_audit_path.exists() and not args.dry_run:
        steps.append(
            run_step(
                [
                    sys.executable,
                    "tools/phase16_live_feature_audit.py",
                    "--date",
                    args.date,
                    "--season",
                    str(args.season),
                    "--markets",
                    *args.markets,
                    "--write",
                ]
            )
        )

    status = "ok" if all(step["returncode"] == 0 for step in steps) else "error"
    print(json.dumps({"status": status, "date": args.date, "season": args.season, "markets": args.markets, "steps": steps}, indent=2))
    if status != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
