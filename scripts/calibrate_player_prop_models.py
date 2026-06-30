from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.player_prop_model_calibration_service import PlayerPropModelCalibrationService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate MLB player prop model probabilities from historical labeled props.")
    parser.add_argument("--market", required=True, help="Market key, e.g. batter_hits.")
    parser.add_argument("--input", default="", help="Historical labeled prop CSV. Defaults to data/training/historical_props_from_ml_labels_joined.csv.")
    parser.add_argument("--out", default="", help="Calibration artifact path. Defaults to data/models/calibration/player_prop_calibration_<market>.joblib.")
    parser.add_argument("--method", choices=("isotonic", "platt"), default="isotonic")
    parser.add_argument("--min-sample", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    service = PlayerPropModelCalibrationService(settings=Settings.from_env(ROOT), min_sample=args.min_sample)
    payload = service.calibrate(
        input_path=Path(args.input) if args.input else None,
        market=args.market,
        method=args.method,
        output_path=Path(args.out) if args.out else None,
        min_sample=args.min_sample,
        dry_run=args.dry_run,
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
