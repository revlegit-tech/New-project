from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from propline_value_client import (
    PLAYER_MARKETS,
    get_events,
    get_event_player_props,
    value_client_status,
)


def event_date(event: dict[str, Any]) -> str:
    raw = str(event.get("commence_time") or event.get("commenceTime") or event.get("date") or "")
    return raw[:10]


def main() -> None:
    parser = argparse.ArgumentParser(description="Token-aware PropLine smoke test.")
    parser.add_argument("--date", default=datetime.utcnow().strftime("%Y-%m-%d"))
    parser.add_argument("--max-events", type=int, default=2)
    parser.add_argument("--pull-props", action="store_true")
    args = parser.parse_args()

    events = [event for event in get_events() if event_date(event) == args.date]

    output = {
        "status": value_client_status(),
        "date": args.date,
        "eventsFound": len(events),
        "eventsPreview": events[: args.max_events],
        "props": [],
    }

    if args.pull_props:
        for event in events[: args.max_events]:
            event_id = str(event.get("id") or "")
            if not event_id:
                continue
            odds = get_event_player_props(event_id, markets=PLAYER_MARKETS)
            output["props"].append({
                "eventId": event_id,
                "homeTeam": event.get("home_team"),
                "awayTeam": event.get("away_team"),
                "bookmakers": len(odds.get("bookmakers", []) or []) if isinstance(odds, dict) else 0,
            })

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
