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
    LEAKAGE_FEATURES,
    IDENTIFIER_ONLY_FEATURES,
    atomic_write_json,
    eligible_live_features,
    metadata_features,
)


def contract_for_market(market: str) -> dict[str, Any]:
    features = metadata_features(market)
    eligible = eligible_live_features(features)
    blocked = [feature for feature in features if feature not in eligible]
    return {
        "market": market,
        "metadataFeatures": features,
        "eligibleLiveFeatures": eligible,
        "blockedFeatures": blocked,
        "leakageFeatures": [feature for feature in blocked if feature in LEAKAGE_FEATURES],
        "identifierOnlyFeatures": [feature for feature in blocked if feature in IDENTIFIER_ONLY_FEATURES],
        "status": "warning" if blocked else "ok",
        "productionNote": "Retrain without blocked features before promotion." if blocked else "Live feature contract is clean.",
    }


def run(markets: list[str], write: bool = False) -> dict[str, Any]:
    results = [contract_for_market(market) for market in markets]
    report = {
        "status": "ok",
        "markets": results,
        "warnings": [
            f"{row['market']}: blocked features {', '.join(row['blockedFeatures'])}"
            for row in results
            if row["blockedFeatures"]
        ],
    }
    if write:
        atomic_write_json(AUDIT_DIR / "phase16_live_feature_contract.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 16 live model feature contract.")
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.markets, write=args.write), indent=2))


if __name__ == "__main__":
    main()
