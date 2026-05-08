#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mlb_app.contracts.data_contracts import default_contracts, validate_contracts


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local MLB app CSV data contracts")
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--season", type=int, required=True, help="Season year, e.g. 2026")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).resolve()
    results = validate_contracts(root, default_contracts(args.season))
    failures = [result for result in results if result.status == "failed"]
    missing = [result for result in results if result.status == "missing"]

    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2, sort_keys=True))
    else:
        for result in results:
            detail = f"{result.name}: {result.status} ({result.path})"
            if result.row_count:
                detail += f" rows={result.row_count}"
            print(detail)
            for column in result.missing_columns:
                print(f"  missing column: {column}")
            for error in result.type_errors:
                print(f"  type error: {error}")
            for warning in result.warnings:
                print(f"  warning: {warning}")

    return 1 if failures or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
