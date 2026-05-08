from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORTS))

from tools.phase14_common import (
    DEFAULT_MARKETS,
    MARKET_FIELDS,
    NUMERIC_FEATURE_CANDIDATES,
    PLAYERBOARD_DIR,
    PREDICTIONS_DIR,
    as_float,
    first_present,
    infer_binary_target,
    market_training_path,
    normalize_market,
    read_csv_rows,
    stable_row_key,
    summarize_training_file,
    write_csv_rows,
)


def candidate_sources() -> list[Path]:
    sources: list[Path] = []
    sources.extend(sorted(PLAYERBOARD_DIR.glob("playerboard_*.csv")))
    sources.extend(sorted(PREDICTIONS_DIR.glob("*.csv")))
    sources.extend(sorted((Path.cwd() / "data" / "backtests").glob("*.csv")))
    return [path for path in sources if path.exists()]


def normalize_training_row(row: dict[str, Any], market: str, source: Path) -> dict[str, Any] | None:
    row_market = normalize_market(first_present(row, MARKET_FIELDS))
    if row_market != market:
        return None
    target = infer_binary_target(row)
    if target is None:
        return None
    out: dict[str, Any] = {
        "date": row.get("date") or row.get("gameDate") or row.get("slateDate") or "",
        "player": row.get("player") or row.get("player_name") or row.get("name") or "",
        "market": market,
        "line": row.get("line") or "",
        "target": target,
        "source_file": str(source),
    }
    for key in NUMERIC_FEATURE_CANDIDATES:
        value = as_float(row.get(key))
        if value is not None:
            out[key] = value
    # Preserve useful categorical context without forcing the trainer to use it.
    for key in ["team", "opponent", "pitcher", "rawLabel", "side", "recommendation", "confidence"]:
        if key in row and row[key] not in (None, ""):
            out[key] = row[key]
    return out


def expand_market(market: str) -> dict[str, Any]:
    base_path = market_training_path(market)
    expanded_path = market_training_path(market, expanded=True)
    base_rows = read_csv_rows(base_path)
    merged: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in base_rows:
        key = stable_row_key({**row, "market": normalize_market(row.get("market") or market)})
        merged[key] = row
    added = 0
    skipped_unlabeled = 0
    scanned = 0
    for source in candidate_sources():
        for row in read_csv_rows(source):
            scanned += 1
            normalized = normalize_training_row(row, market, source)
            if normalized is None:
                if normalize_market(first_present(row, MARKET_FIELDS)) == market:
                    skipped_unlabeled += 1
                continue
            key = stable_row_key(normalized)
            if key not in merged:
                merged[key] = normalized
                added += 1
    rows = list(merged.values())
    return {
        "market": market,
        "basePath": str(base_path),
        "expandedPath": str(expanded_path),
        "baseRows": len(base_rows),
        "expandedRows": len(rows),
        "addedRows": added,
        "scannedRows": scanned,
        "skippedUnlabeledRowsForMarket": skipped_unlabeled,
        "rows": rows,
        "summary": summarize_rows(rows),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pos = 0
    neg = 0
    unlabeled = 0
    for row in rows:
        label = infer_binary_target(row)
        if label == 1:
            pos += 1
        elif label == 0:
            neg += 1
        else:
            unlabeled += 1
    return {
        "rows": len(rows),
        "labeledRows": pos + neg,
        "positiveRows": pos,
        "negativeRows": neg,
        "unlabeledRows": unlabeled,
        "twoClass": pos > 0 and neg > 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand market training data from explicitly labeled local sources.")
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--replace-base", action="store_true", help="Also replace data/training/<market>_training.csv with expanded rows.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = []
    for market in args.markets:
        result = expand_market(market)
        rows = result.pop("rows")
        if args.write:
            write_csv_rows(Path(result["expandedPath"]), rows)
            if args.replace_base and result["summary"]["twoClass"]:
                write_csv_rows(Path(result["basePath"]), rows)
        results.append(result)
    payload = {"status": "ok", "dryRun": not args.write, "results": results}
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
