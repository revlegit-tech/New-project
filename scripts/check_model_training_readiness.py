from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.model_training_readiness_service import ModelTrainingReadinessService


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run MLB prop model training readiness gates.")
    parser.add_argument("--date", default="today")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--market", default="")
    parser.add_argument("--train-baseline", action="store_true", help="Reserved explicit training switch; Sprint 30 does not train.")
    args = parser.parse_args()

    payload = ModelTrainingReadinessService().payload(
        date_label=args.date,
        season=args.season,
        market=args.market or None,
    )
    if args.train_baseline:
        payload["trainingRequested"] = True
        payload["modelTrainingTriggered"] = False
        payload.setdefault("warnings", []).append("Baseline training is not implemented in Sprint 30; readiness dry-run only.")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 2 if args.train_baseline else 0


if __name__ == "__main__":
    raise SystemExit(main())
