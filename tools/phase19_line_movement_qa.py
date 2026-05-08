from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_DIR = ROOT / "data" / "warehouse" / "game_context"

FIELDS = [
    "team", "opponent", "team_moneyline", "opponent_moneyline", "game_total",
    "open_team_moneyline", "close_team_moneyline", "moneyline_move",
    "open_game_total", "close_game_total", "total_move", "line_snapshot_count",
    "line_movement_status", "line_movement_source",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def main() -> None:
    parser = argparse.ArgumentParser(description="QA Phase 19 game-context line movement fields.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    rows = read_rows(CONTEXT_DIR / f"game_context_{args.date}.csv")
    sample = [{field: clean(row.get(field)) for field in FIELDS} for row in rows[: args.limit]]
    missing = {
        field: sum(1 for row in rows if not clean(row.get(field)))
        for field in ["open_team_moneyline", "close_team_moneyline", "open_game_total", "close_game_total", "line_snapshot_count", "line_movement_status"]
    }
    print(json.dumps({"status": "ok" if rows else "warning", "rows": len(rows), "sample": sample, "missingByField": missing}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
