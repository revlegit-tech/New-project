from __future__ import annotations

import argparse
import json
from datetime import datetime

from mlb_app.services.propline_props_service import PROPLINE_MARKETS, PropLineSyncRequest, sync_propline_props


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PropLine MLB player props and save local source CSV/snapshot.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--sport", default="baseball_mlb")
    parser.add_argument("--markets", default=",".join(PROPLINE_MARKETS))
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--no-snapshot", action="store_true")
    args = parser.parse_args()

    markets = tuple(part.strip() for part in args.markets.split(",") if part.strip())
    payload = sync_propline_props(
        PropLineSyncRequest(
            date=args.date,
            sport=args.sport,
            markets=markets,
            save=not args.no_save,
            snapshot=not args.no_snapshot,
        )
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
