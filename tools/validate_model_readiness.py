#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings  # noqa: E402
from mlb_app.services.model_registry_service import DEFAULT_MARKETS, ModelRegistryService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate market model readiness gates.")
    parser.add_argument("--markets", nargs="*", default=list(DEFAULT_MARKETS))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-production", action="store_true", help="Exit non-zero unless at least one market is production eligible.")
    args = parser.parse_args()

    service = ModelRegistryService(Settings.from_env(ROOT))
    payload = service.status_payload(tuple(args.markets))
    issues = []
    if args.require_production and not payload.get("productionEligibleMarkets"):
        issues.append("No production-eligible markets found.")
    for row in payload.get("markets", []):
        if row.get("status") in {"production", "production_candidate"} and not row.get("productionEligible"):
            issues.append(f"{row.get('market')}: production status did not satisfy all gates")

    result = {"status": "failed" if issues else "ok", "issues": issues, **payload}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Model readiness: {result['status']}")
        for row in result.get("markets", []):
            prod = "yes" if row.get("productionEligible") else "no"
            print(
                f"- {row.get('market')}: {row.get('status')} | "
                f"trained={row.get('modelTrained')} | calibrated={row.get('calibrated')} | "
                f"rows={row.get('trainingRows')} | production={prod} | {row.get('reason')}"
            )
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)

    raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    main()
