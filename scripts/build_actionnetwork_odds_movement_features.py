from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.actionnetwork_odds_movement_service import (
    ActionNetworkOddsMovementService,
    load_timestamped_snapshots,
    read_csv,
    write_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build pregame ActionNetwork odds movement features.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--odds-dir", default="data/warehouse/normalized/odds")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    rows = []
    for path in load_timestamped_snapshots(Path(args.odds_dir), args.date):
        rows.extend(read_csv(path))

    feature_rows = ActionNetworkOddsMovementService().build_feature_rows(rows)
    output = Path(args.output) if args.output else Path("data/warehouse/features") / f"actionnetwork_odds_movement_features_{args.date}.csv"
    write_csv(output, feature_rows)
    print(f"features_csv={output}")
    print(f"rows={len(feature_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
