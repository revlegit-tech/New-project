from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.model_backtest_service import ModelBacktestService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest or dry-run baseline player prop model evaluation.")
    parser.add_argument("--date", default=None, help="Slate date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--season", type=int, default=0, help="MLB season. Defaults to configured current season.")
    parser.add_argument("--market", required=True, help="Player prop market, e.g. batter_hits.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Inspect backtest inputs without writing artifacts.")
    mode.add_argument("--backtest", action="store_true", help="Explicitly write backtest artifacts when inputs exist.")
    args = parser.parse_args(argv)

    service = ModelBacktestService(Settings.from_env(ROOT))
    payload = service.backtest(
        date_label=args.date,
        season=args.season or None,
        market=args.market,
        backtest=bool(args.backtest),
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
