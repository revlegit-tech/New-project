from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.actionnetwork_odds_movement_service import read_csv
from mlb_app.services.actionnetwork_training_dataset_service import (
    ActionNetworkTrainingDatasetService,
    write_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build event-confirmed ActionNetwork ML training dataset.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--labels-path", default=None)
    parser.add_argument("--features-path", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--summary-output", default=None)
    args = parser.parse_args()

    labels_path = Path(args.labels_path) if args.labels_path else Path("data/warehouse/ml_labels") / f"actionnetwork_prop_labels_{args.season}.csv"
    features_path = Path(args.features_path) if args.features_path else Path("data/warehouse/features") / f"actionnetwork_odds_movement_features_{args.date}.csv"
    output = Path(args.output) if args.output else Path("data/warehouse/training") / f"actionnetwork_training_dataset_{args.date}.csv"
    summary = Path(args.summary_output) if args.summary_output else Path("data/warehouse/training") / f"actionnetwork_training_dataset_summary_{args.date}.json"

    rows, manifest = ActionNetworkTrainingDatasetService().build_rows(
        labels=read_csv(labels_path),
        movement_features=read_csv(features_path),
    )
    write_dataset(output, summary, rows, manifest)
    print(f"training_csv={output}")
    print(f"summary_json={summary}")
    print(f"trainable_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
