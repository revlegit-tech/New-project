from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def coverage(rows: list[dict[str, str]], fields: list[str]) -> dict[str, Any]:
    total = len(rows)
    return {
        "rows": total,
        "fields": [
            {"field": field, "presentRows": sum(1 for row in rows if clean(row.get(field))), "coverage": round(sum(1 for row in rows if clean(row.get(field))) / max(1, total), 4)}
            for field in fields
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="QA Phase 22 OddsPapi context enrichment.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    context_path = DATA / "warehouse" / "game_context" / f"game_context_{args.date}.csv"
    audit_path = DATA / "warehouse" / "audits" / f"phase22_oddspapi_clv_{args.date}.json"
    rows = read_csv(context_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {"status": "missing"}
    fields = [
        "oddspapi_fixture_id",
        "oddspapi_provider_status",
        "open_team_moneyline",
        "close_team_moneyline",
        "moneyline_move",
        "open_game_total",
        "close_game_total",
        "total_move",
        "line_movement_source",
        "line_movement_status",
    ]
    print(json.dumps({
        "status": "ok" if rows and audit.get("status") in {"ok", "warning", "skipped"} else "warning",
        "date": args.date,
        "auditStatus": audit.get("status"),
        "auditReason": audit.get("reason", ""),
        "providerClvReadyRows": audit.get("providerClvReadyRows", 0),
        "coverage": coverage(rows, fields),
        "sample": rows[:2],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
