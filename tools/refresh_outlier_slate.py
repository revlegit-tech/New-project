from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.propline_props_service import PROPLINE_MARKETS, PropLineSyncRequest, sync_propline_props


def run_playerboard(date_label: str, season: int, limit: int, market: str, source_mode: str) -> dict:
    from playerboard import build_playerboard

    return build_playerboard(
        season=season,
        date_label=date_label,
        market=market,
        limit=limit,
        save=True,
        replace_date=True,
        source_mode=source_mode,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch fresh PropLine props and rebuild the Outlier Playerboard for one slate.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--sport", default="baseball_mlb")
    parser.add_argument("--markets", default=",".join(PROPLINE_MARKETS))
    parser.add_argument("--market", default="", help="Optional single Playerboard market to rebuild.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--max-events", type=int, default=0, help="Optional PropLine event cap. 0 means all matching events.")
    parser.add_argument("--skip-fetch", action="store_true", help="Use existing data/odds/propline_props_DATE.csv and only rebuild Playerboard.")
    parser.add_argument("--source-mode", choices=["auto", "canonical", "legacy"], default="canonical", help="Playerboard prop source mode. Canonical prevents legacy stale files from mixing into a dated slate.")
    args = parser.parse_args()

    markets = tuple(part.strip() for part in args.markets.split(",") if part.strip())
    sync_payload = {"status": "skipped"}
    if not args.skip_fetch:
        sync_payload = sync_propline_props(
            PropLineSyncRequest(
                date=args.date,
                sport=args.sport,
                markets=markets,
                save=True,
                snapshot=True,
                max_events=args.max_events,
            )
        )

    board_payload = run_playerboard(
        date_label=args.date,
        season=args.season,
        limit=args.limit,
        market=args.market,
        source_mode=args.source_mode,
    )

    print(json.dumps({"status": "ok", "sync": sync_payload, "playerboard": board_payload}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
