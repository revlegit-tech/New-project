from __future__ import annotations

import argparse
import json
from typing import Any

from mlb_app.services.edge_board_service import EdgeBoardService

FIELDS = [
    "player", "team", "opponent", "team_moneyline", "opponent_moneyline", "game_total",
    "moneyline_implied_probability", "team_implied_runs", "opponent_implied_runs",
    "weather_temperature_f", "weather_wind_mph", "weather_humidity", "weather_wind_direction", "roof_status",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--market", default="batter_hits")
    parser.add_argument("--limit", default="5")
    args = parser.parse_args()

    payload = EdgeBoardService().payload({
        "date": [args.date],
        "market": [args.market],
        "limit": [str(args.limit)],
        "refresh": ["1"],
    })
    rows = payload.get("rows") or []
    sample = [{field: row.get(field, "") for field in FIELDS} for row in rows[: int(args.limit)]]
    missing = {field: sum(1 for row in sample if not clean(row.get(field))) for field in FIELDS[3:]}
    status = "ok" if sample and all(count == 0 for count in missing.values()) else "warning"
    print(json.dumps({"status": status, "rows": len(rows), "sample": sample, "missingByFieldInSample": missing}, indent=2))


if __name__ == "__main__":
    main()
