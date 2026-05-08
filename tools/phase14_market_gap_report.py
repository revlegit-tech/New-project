from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORTS))

from tools.phase14_common import (
    DEFAULT_MARKETS,
    load_registry,
    market_training_path,
    model_artifact_path,
    model_features_path,
    production_gate_status,
    registry_markets,
    summarize_training_file,
)


def build_report(markets: list[str]) -> dict:
    registry = load_registry()
    entries = registry_markets(registry)
    market_reports = []
    for market in markets:
        base = summarize_training_file(market_training_path(market))
        expanded = summarize_training_file(market_training_path(market, expanded=True))
        training = expanded if expanded["exists"] and expanded["labeledRows"] >= base["labeledRows"] else base
        entry = entries.get(market, {}) if isinstance(entries, dict) else {}
        gate = production_gate_status(entry)
        artifact_exists = model_artifact_path(market).exists()
        metadata_exists = model_features_path(market).exists()
        blockers = []
        if not training["twoClass"]:
            blockers.append("training data does not have both classes")
        if training["labeledRows"] < 25:
            blockers.append("less than 25 labeled training rows")
        if not artifact_exists:
            blockers.append("missing model artifact")
        if not metadata_exists:
            blockers.append("missing feature metadata")
        blockers.extend(f"production gate missing: {name}" for name in gate["missing"])
        market_reports.append(
            {
                "market": market,
                "training": training,
                "baseTraining": base,
                "expandedTraining": expanded,
                "artifactExists": artifact_exists,
                "metadataExists": metadata_exists,
                "registryStatus": entry.get("status", "missing"),
                "calibrated": bool(entry.get("calibrated")),
                "backtest": entry.get("backtest") or {},
                "productionGate": gate,
                "productionEligible": gate["ok"],
                "blockers": blockers,
            }
        )
    return {
        "status": "ok",
        "markets": market_reports,
        "productionEligibleMarkets": [m["market"] for m in market_reports if m["productionEligible"]],
        "trainableMarkets": [m["market"] for m in market_reports if m["training"]["twoClass"] and m["training"]["labeledRows"] >= 25],
        "needsMoreLabels": [m["market"] for m in market_reports if not m["training"]["twoClass"] or m["training"]["labeledRows"] < 25],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Phase 14 market training/backtest gaps.")
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(args.markets)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print("Phase 14 market gap report")
    for item in report["markets"]:
        training = item["training"]
        gate = item["productionGate"]
        print(f"- {item['market']}: labels={training['labeledRows']} classCounts={training['classCounts']} status={item['registryStatus']} production={gate['ok']}")
        for blocker in item["blockers"][:5]:
            print(f"    blocker: {blocker}")


if __name__ == "__main__":
    main()
