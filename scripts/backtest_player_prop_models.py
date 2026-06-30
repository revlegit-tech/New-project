from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.player_prop_model_backtest_service import PlayerPropModelBacktestService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest MLB player prop model predictions by market and edge bucket.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--input", default="", help="Historical labeled prop CSV. Defaults to data/training/historical_props_from_ml_labels_joined.csv.")
    parser.add_argument("--out", default="", help="Backtest CSV output path.")
    parser.add_argument("--summary-out", default="", help="Backtest summary JSON output path.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    service = PlayerPropModelBacktestService(settings=Settings.from_env(ROOT))
    report = service.backtest(
        season=args.season,
        input_path=Path(args.input) if args.input else None,
        output_path=Path(args.out) if args.out else None,
        summary_path=Path(args.summary_out) if args.summary_out else None,
        dry_run=args.dry_run,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
