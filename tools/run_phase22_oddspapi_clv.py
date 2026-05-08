from __future__ import annotations

import argparse
import json
from phase22_oddspapi_clv import run_phase22


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 22 OddsPapi CLV enrichment.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--bookmakers", nargs="*", default=None)
    parser.add_argument("--no-apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_phase22(args.date, args.season, apply=not args.no_apply, bookmakers=args.bookmakers), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
