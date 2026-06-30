from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.player_prop_model_scoring_service import PlayerPropModelScoringService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score MLB player props with exact trained market model artifacts.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--source", choices=("playerboard", "features"), default="playerboard")
    parser.add_argument("--features", default="", help="Optional feature CSV path.")
    parser.add_argument("--playerboard", default="", help="Optional playerboard CSV path.")
    parser.add_argument("--out", default="", help="Prediction CSV output path.")
    parser.add_argument("--summary-out", default="", help="Prediction summary JSON output path.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env(ROOT)
    service = PlayerPropModelScoringService(settings=settings)
    report = service.score(
        date_label=args.date,
        season=args.season,
        source=args.source,
        features_path=Path(args.features) if args.features else None,
        playerboard_path=Path(args.playerboard) if args.playerboard else None,
        out_path=Path(args.out) if args.out else None,
        summary_out_path=Path(args.summary_out) if args.summary_out else None,
        dry_run=args.dry_run,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
