from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.actionnetwork_snapshot_status_service import ActionNetworkSnapshotWorkflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one locked ActionNetwork live snapshot workflow.")
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today.")
    parser.add_argument("--market", default="all")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()

    date_text = date.today().isoformat() if args.date == "today" else args.date
    payload = ActionNetworkSnapshotWorkflow(Settings.from_env(ROOT)).run(
        date_text=date_text,
        market=args.market,
        refresh=args.refresh,
        retries=max(0, args.retries),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") in {"success", "warning", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
