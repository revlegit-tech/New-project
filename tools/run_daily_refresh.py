from __future__ import annotations

"""Phase 21 daily refresh wrapper.

This script provides one operator-safe command for the normal daily data refresh.
It wraps season_auto_collector.py, then writes a freshness report that the UI and
operators can use to verify that PropLine, game context, weather, line movement,
and Playerboard outputs were updated.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "data" / "warehouse" / "audits"

VALID_RUN_TYPES = {"scheduled", "morning", "midday", "midnight", "manual", "grading"}
COLLECTOR_RUN_TYPES = {"morning", "midday", "midnight", "manual", "grading"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_run_type(run_type: str, *, local_hour: int | None = None) -> str:
    """Resolve operator-friendly run type to the collector's supported run type."""
    value = (run_type or "manual").strip().lower()
    if value not in VALID_RUN_TYPES:
        raise ValueError(f"Unsupported run type: {run_type}")
    if value != "scheduled":
        return value

    hour = datetime.now().hour if local_hour is None else int(local_hour)
    if 0 <= hour < 11:
        return "morning"
    if 11 <= hour < 18:
        return "midday"
    return "midnight"


def run_command(args: list[str], *, timeout: int) -> dict[str, Any]:
    started = now_iso()
    try:
        proc = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "status": "ok" if proc.returncode == 0 else "warning",
            "returncode": proc.returncode,
            "command": " ".join(args),
            "startedAt": started,
            "finishedAt": now_iso(),
            "stdoutTail": (proc.stdout or "")[-8000:],
            "stderrTail": (proc.stderr or "")[-8000:],
        }
    except subprocess.TimeoutExpired as error:
        return {
            "status": "warning",
            "returncode": None,
            "command": " ".join(args),
            "startedAt": started,
            "finishedAt": now_iso(),
            "error": f"Timed out after {timeout} seconds",
            "stdoutTail": (error.stdout or "")[-8000:] if isinstance(error.stdout, str) else "",
            "stderrTail": (error.stderr or "")[-8000:] if isinstance(error.stderr, str) else "",
        }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 21 daily MLB refresh wrapper.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--run-type", default="manual", choices=sorted(VALID_RUN_TYPES))
    parser.add_argument("--include-savant", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--skip-collector", action="store_true", help="Only write freshness report.")
    args = parser.parse_args()

    if not str(args.date).startswith(str(args.season)):
        raise SystemExit(f"--season {args.season} does not match --date {args.date}")

    collector_run_type = resolve_run_type(args.run_type)
    result: dict[str, Any] = {
        "status": "ok",
        "phase": "21",
        "date": args.date,
        "season": args.season,
        "requestedRunType": args.run_type,
        "collectorRunType": collector_run_type,
        "startedAt": now_iso(),
        "collector": {"status": "skipped", "reason": "--skip-collector"},
        "freshness": None,
    }

    if not args.skip_collector:
        cmd = [
            sys.executable,
            str(ROOT / "season_auto_collector.py"),
            "snapshot",
            "--date",
            args.date,
            "--run-type",
            collector_run_type,
        ]
        if args.include_savant:
            cmd.append("--include-savant")
        result["collector"] = run_command(cmd, timeout=args.timeout_seconds)

    freshness_cmd = [
        sys.executable,
        str(ROOT / "tools" / "phase21_freshness_report.py"),
        "--date",
        args.date,
        "--season",
        str(args.season),
        "--write",
    ]
    result["freshnessCommand"] = run_command(freshness_cmd, timeout=180)
    freshness_path = AUDIT_DIR / f"phase21_freshness_{args.date}.json"
    if freshness_path.exists():
        try:
            result["freshness"] = json.loads(freshness_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result["freshness"] = {"status": "warning", "error": "Could not parse freshness JSON."}

    if result.get("collector", {}).get("status") == "warning":
        result["status"] = "warning"
    if isinstance(result.get("freshness"), dict) and result["freshness"].get("status") == "warning":
        result["status"] = "warning"

    result["finishedAt"] = now_iso()
    output_path = AUDIT_DIR / f"phase21_daily_refresh_{args.date}_{collector_run_type}.json"
    write_json(output_path, result)
    result["outputPath"] = str(output_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
