from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone


ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORTS))

from tools.phase14_common import DEFAULT_MARKETS, load_registry, production_gate_status, registry_markets, save_registry


def promote(markets: list[str], *, write: bool = False) -> dict:
    registry = load_registry()
    entries = registry_markets(registry)
    results = []
    for market in markets:
        entry = entries.get(market, {}) if isinstance(entries, dict) else {}
        gate = production_gate_status(entry)
        before = entry.get("status", "missing")
        after = before
        if gate["ok"]:
            after = "production"
            if write:
                entry["status"] = "production"
                entry["promoted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                entry["promotion_gate"] = gate
        else:
            if before == "production":
                after = "experimental"
                if write:
                    entry["status"] = "experimental"
                    entry["demoted_reason"] = f"Failed production gates: {', '.join(gate['missing'])}"
        results.append({"market": market, "before": before, "after": after, "productionEligible": gate["ok"], "gate": gate})
    if write:
        save_registry(registry)
    return {"status": "ok", "dryRun": not write, "results": results, "productionEligibleMarkets": [r["market"] for r in results if r["productionEligible"]]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote market models only if Phase 14 production gates pass.")
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(promote(args.markets, write=args.write), indent=2))


if __name__ == "__main__":
    main()
