from __future__ import annotations

import argparse
import json
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase15_common import (
    DEFAULT_MARKETS,
    base_training_path,
    class_counts,
    dedupe_key,
    expanded_training_path,
    feature_columns_for_market,
    label_value,
    quality_training_path,
    read_csv_rows,
    summarize_training_rows,
    write_csv_rows,
)


def choose_rows(market: str, min_feature_coverage: float = 0.6) -> dict[str, Any]:
    base_rows = read_csv_rows(base_training_path(market))
    expanded_rows = read_csv_rows(expanded_training_path(market))
    source_rows = base_rows + expanded_rows
    features = feature_columns_for_market(market, source_rows)
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    rejected = {"unlabeled": 0, "duplicate": 0, "sparseFeatures": 0}

    for row in source_rows:
        label = label_value(row)
        if label is None:
            rejected["unlabeled"] += 1
            continue
        key = dedupe_key(row, market)
        if key in seen:
            rejected["duplicate"] += 1
            continue
        seen.add(key)
        if features:
            present = sum(1 for feature in features if str(row.get(feature, "")).strip() != "")
            coverage = present / max(1, len(features))
            if coverage < min_feature_coverage:
                rejected["sparseFeatures"] += 1
                continue
        row = dict(row)
        row["over"] = str(label)
        selected.append(row)

    summary = summarize_training_rows(selected)
    return {
        "market": market,
        "baseRows": len(base_rows),
        "expandedRows": len(expanded_rows),
        "qualityRows": len(selected),
        "featureCount": len(features),
        "summary": summary,
        "rejected": rejected,
        "rows": selected,
        "out": str(quality_training_path(market)),
    }


def run(markets: list[str], write: bool = False, min_feature_coverage: float = 0.6) -> dict[str, Any]:
    results = []
    for market in markets:
        result = choose_rows(market, min_feature_coverage=min_feature_coverage)
        rows = result.pop("rows")
        if write:
            write_csv_rows(quality_training_path(market), rows)
        results.append(result)
    return {"status": "ok", "dryRun": not write, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 15 quality training datasets.")
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--min-feature-coverage", type=float, default=0.6)
    args = parser.parse_args()
    print(json.dumps(run(args.markets, write=args.write, min_feature_coverage=args.min_feature_coverage), indent=2))


if __name__ == "__main__":
    main()
