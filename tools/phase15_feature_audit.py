from __future__ import annotations

import argparse
import json
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase15_common import (
    AUDIT_DIR,
    DEFAULT_MARKETS,
    atomic_write_json,
    base_training_path,
    expanded_training_path,
    feature_columns_for_market,
    feature_coverage,
    market_rows_from_playerboard,
    metadata_features,
    quality_training_path,
    read_csv_rows,
)


def audit_market(market: str, season: int, date: str | None = None) -> dict[str, Any]:
    paths = {
        "baseTraining": base_training_path(market),
        "expandedTraining": expanded_training_path(market),
        "qualityTraining": quality_training_path(market),
    }
    training_rows = read_csv_rows(paths["qualityTraining"]) or read_csv_rows(paths["expandedTraining"]) or read_csv_rows(paths["baseTraining"])
    live_rows = market_rows_from_playerboard(market, season=season, date=date)
    features = metadata_features(market) or feature_columns_for_market(market, training_rows)
    training_cov = feature_coverage(training_rows, features)
    live_cov = feature_coverage(live_rows, features)
    missing_live = [item["feature"] for item in live_cov["features"] if item["numericCoverage"] == 0]
    sparse_live = [item["feature"] for item in live_cov["features"] if 0 < item["numericCoverage"] < 0.8]
    return {
        "market": market,
        "date": date,
        "season": season,
        "paths": {name: str(path) for name, path in paths.items()},
        "trainingRows": len(training_rows),
        "liveRows": len(live_rows),
        "metadataFeatureCount": len(metadata_features(market)),
        "featureCount": len(features),
        "trainingFeatureCoverage": training_cov,
        "liveFeatureCoverage": live_cov,
        "missingLiveFeatures": missing_live,
        "sparseLiveFeatures": sparse_live,
        "status": "ok" if live_rows and not missing_live else "warning",
    }


def build_report(markets: list[str], season: int, date: str | None = None) -> dict[str, Any]:
    rows = [audit_market(market, season=season, date=date) for market in markets]
    return {
        "status": "ok",
        "season": season,
        "date": date,
        "markets": rows,
        "warnings": [
            f"{row['market']}: missing live features {', '.join(row['missingLiveFeatures'])}"
            for row in rows
            if row["missingLiveFeatures"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Phase 15 model feature coverage.")
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--date", default=None)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    report = build_report(args.markets, season=args.season, date=args.date)
    if args.write:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_json(AUDIT_DIR / "phase15_feature_audit.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
