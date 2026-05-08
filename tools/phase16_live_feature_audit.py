from __future__ import annotations

import argparse
import json
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase16_common import (
    AUDIT_DIR,
    DEFAULT_MARKETS,
    LIVE_FEATURES,
    atomic_write_json,
    eligible_live_features,
    feature_coverage,
    filter_rows,
    metadata_features,
    playerboard_path,
    read_csv_rows,
)


def audit_market(market: str, season: int, date: str | None = None) -> dict[str, Any]:
    board_rows = filter_rows(read_csv_rows(playerboard_path(season)), market=market, date=date)
    model_features = metadata_features(market)
    eligible_model_features = eligible_live_features(model_features)
    expected = []
    for feature in eligible_model_features + LIVE_FEATURES:
        if feature not in expected:
            expected.append(feature)
    coverage = feature_coverage(board_rows, expected)
    missing = [item["feature"] for item in coverage["features"] if item["numericCoverage"] == 0]
    sparse = [item["feature"] for item in coverage["features"] if 0 < item["numericCoverage"] < 0.8]
    leakage = [feature for feature in model_features if feature not in eligible_model_features]
    return {
        "market": market,
        "season": season,
        "date": date,
        "rows": len(board_rows),
        "modelFeatureCount": len(model_features),
        "eligibleModelFeatureCount": len(eligible_model_features),
        "blockedModelFeatures": leakage,
        "expectedLiveFeatures": expected,
        "coverage": coverage,
        "missingLiveFeatures": missing,
        "sparseLiveFeatures": sparse,
        "status": "ok" if board_rows and not missing else "warning",
    }


def build_report(markets: list[str], season: int, date: str | None = None, write: bool = False) -> dict[str, Any]:
    results = [audit_market(market, season=season, date=date) for market in markets]
    report = {
        "status": "ok",
        "season": season,
        "date": date,
        "markets": results,
        "warnings": [
            f"{row['market']}: missing live features {', '.join(row['missingLiveFeatures'])}"
            for row in results
            if row["missingLiveFeatures"]
        ],
        "blockedFeatureWarnings": [
            f"{row['market']}: model metadata contains non-live/leakage features {', '.join(row['blockedModelFeatures'])}"
            for row in results
            if row["blockedModelFeatures"]
        ],
    }
    if write:
        suffix = date or "latest"
        atomic_write_json(AUDIT_DIR / f"phase16_live_feature_audit_{suffix}.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit live Playerboard feature parity for model inputs.")
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--date", default=None)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_report(args.markets, season=args.season, date=args.date, write=args.write), indent=2))


if __name__ == "__main__":
    main()
