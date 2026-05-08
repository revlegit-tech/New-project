from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase17_common import (  # noqa: E402
    AUDIT_DIR,
    CONTEXT_FIELDS,
    DEFAULT_MARKETS,
    STRING_CONTEXT_FIELDS,
    atomic_write_json,
    feature_coverage,
    filter_rows,
    playerboard_path,
    read_csv_rows,
)


def audit_market(market: str, season: int, date: str) -> dict[str, Any]:
    rows = filter_rows(read_csv_rows(playerboard_path(season)), market=market, date=date)
    coverage = feature_coverage(rows, CONTEXT_FIELDS, string_fields=STRING_CONTEXT_FIELDS)
    missing = []
    sparse = []
    for item in coverage["features"]:
        # For string fields, numericCoverage is intentionally equivalent to presence.
        if item["numericCoverage"] == 0:
            missing.append(item["feature"])
        elif item["numericCoverage"] < 0.8:
            sparse.append(item["feature"])
    critical_missing = [
        field
        for field in missing
        if field
        in {
            "team_moneyline",
            "opponent_moneyline",
            "game_total",
            "team_implied_runs",
            "opponent_implied_runs",
            "park_factor",
        }
    ]
    return {
        "market": market,
        "season": season,
        "date": date,
        "rows": len(rows),
        "coverage": coverage,
        "missingContextFeatures": missing,
        "sparseContextFeatures": sparse,
        "criticalMissingContextFeatures": critical_missing,
        "status": "ok" if rows and not critical_missing else "warning",
    }


def audit(markets: list[str], season: int, date: str, write: bool = False) -> dict[str, Any]:
    results = [audit_market(market, season, date) for market in markets]
    warnings = []
    for result in results:
        if result["rows"] == 0:
            warnings.append(f"{result['market']}: no rows found for {date}")
        if result["criticalMissingContextFeatures"]:
            warnings.append(
                f"{result['market']}: missing critical context " + ", ".join(result["criticalMissingContextFeatures"])
            )
    payload = {
        "status": "ok" if not warnings else "warning",
        "season": season,
        "date": date,
        "markets": results,
        "warnings": warnings,
    }
    if write:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_json(AUDIT_DIR / f"phase17_game_context_audit_{season}_{date}.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Phase 17 game-context coverage for live Playerboard rows.")
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.markets, args.season, args.date, write=args.write), indent=2))


if __name__ == "__main__":
    main()
