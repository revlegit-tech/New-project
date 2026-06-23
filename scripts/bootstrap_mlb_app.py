from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.launch_bootstrap_service import LaunchBootstrapService


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight launch bootstrap for the MLB app.")
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today.")
    parser.add_argument("--skip", action="store_true", help="Write skipped bootstrap status.")
    args = parser.parse_args()

    settings = Settings.from_env(ROOT)
    payload = LaunchBootstrapService(settings).run(date_text=args.date, skip=args.skip)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") in {"success", "warning", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
