from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.baseline_model_training_service import BaselineModelTrainingService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train or dry-run a research-only baseline player prop model.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--season", type=int, default=0, help="MLB season. Defaults to configured current season.")
    parser.add_argument("--market", required=True, help="Player prop market, e.g. batter_hits.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Inspect readiness and planned training without writing artifacts.")
    mode.add_argument("--train", action="store_true", help="Explicitly train and write baseline artifacts when eligible.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(ROOT)
    service = BaselineModelTrainingService(settings)
    payload = service.train(
        date_label=args.date,
        season=args.season or None,
        market=args.market,
        train=bool(args.train),
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
