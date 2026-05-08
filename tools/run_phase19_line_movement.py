from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from tools.phase19_line_movement import run_phase19

ROOT = Path(__file__).resolve().parents[1]


def run_context(date_label: str, season: int, markets: list[str], line_source: str) -> dict[str, object]:
    script = ROOT / "tools" / "phase18_fill_missing_context.py"
    if not script.exists():
        return {"status": "skipped", "reason": "phase18_fill_missing_context.py missing"}
    proc = subprocess.run([
        sys.executable, str(script.relative_to(ROOT)),
        "--date", date_label,
        "--season", str(season),
        "--markets", *markets,
        "--line-source", line_source,
    ], cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "status": "ok" if proc.returncode == 0 else "warning",
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 19 line movement workflow.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--markets", nargs="+", default=["batter_hits", "batter_total_bases"])
    parser.add_argument("--line-source", default="propline", choices=["propline", "the_odds_api", "oddspapi", "auto"])
    parser.add_argument("--skip-context-refresh", action="store_true")
    parser.add_argument("--patch-playerboard", action="store_true")
    args = parser.parse_args()

    context = {"status": "skipped", "reason": "--skip-context-refresh"}
    if not args.skip_context_refresh:
        context = run_context(args.date, args.season, args.markets, "propline" if args.line_source in {"auto", "oddspapi"} else args.line_source)
    movement = run_phase19(args.date, args.season, source=f"phase19_{args.line_source}", patch_playerboard=args.patch_playerboard)
    print(json.dumps({"status": movement.get("status"), "contextRefresh": context, "lineMovement": movement}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
