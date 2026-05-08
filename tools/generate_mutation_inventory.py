#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

MUTATION_KEYWORDS = ("sync", "train", "refresh", "backfill", "catchup", "grade", "upload", "settings", "my-picks", "bankroll", "repair", "import", "collect", "update", "write", "pipeline", "cache")
ADMIN_KEYWORDS = ("sync", "train", "refresh", "backfill", "catchup", "grade", "repair", "pipeline", "upload", "import", "cache")


def classify(row: dict[str, str]) -> tuple[bool, str, str, str]:
    endpoint = row.get("endpoint", "")
    method = row.get("method", "GET").upper()
    text = " ".join(str(row.get(key, "")) for key in row).lower()
    endpoint_lower = endpoint.lower()
    is_mutation = method not in {"GET", "HEAD", "OPTIONS"} or any(word in text for word in MUTATION_KEYWORDS)
    if not is_mutation:
        return False, "", "", ""
    if endpoint in {"/api/my-picks", "/api/my-picks/update"}:
        return True, "product_mutation", "bettor_state", "MEDIUM"
    if endpoint == "/api/bankroll/settings":
        return True, "product_mutation", "risk_controls", "HIGH"
    if any(word in endpoint_lower for word in ADMIN_KEYWORDS) or row.get("classification") == "QUARANTINE":
        return True, "admin_workflow", "ops_data", "HIGH"
    return True, "review_required", row.get("owner") or "TBD", row.get("risk") or "MEDIUM"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 6 mutation endpoint inventory from endpoint triage CSV.")
    parser.add_argument("--triage", default="docs/endpoint-triage/endpoint_triage_inventory.csv")
    parser.add_argument("--out", default="docs/security/mutation_endpoint_inventory.csv")
    args = parser.parse_args()
    rows = list(csv.DictReader(Path(args.triage).open(newline="", encoding="utf-8")))
    fieldnames = ["endpoint", "method", "classification", "mutation_kind", "owner", "risk", "required_boundary", "current_status", "next_action", "notes"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            is_mutation, kind, owner, risk = classify(row)
            if not is_mutation:
                continue
            count += 1
            boundary = "router mutation middleware + rate limit"
            if kind == "admin_workflow" or row.get("classification") == "QUARANTINE":
                boundary = "quarantine behind CLI/scheduler/admin-only route"
            writer.writerow({"endpoint": row.get("endpoint", ""), "method": row.get("method", ""), "classification": row.get("classification", ""), "mutation_kind": kind, "owner": owner, "risk": risk, "required_boundary": boundary, "current_status": row.get("status", ""), "next_action": row.get("next_action", ""), "notes": row.get("notes", "")})
    print(f"wrote {count} mutation/workflow rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
