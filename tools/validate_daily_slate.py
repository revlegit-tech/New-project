from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normal_direction(row: dict[str, str]) -> str:
    raw = _clean(row.get("rawLabel") or row.get("label") or row.get("side")).lower()
    market = _clean(row.get("market") or row.get("baseMarket") or row.get("originalMarket")).lower()
    if raw in {"yes", "1+"} or raw.startswith("over") or raw.startswith("yes "):
        return "over"
    if raw.startswith("under") or raw == "no":
        return "under"
    if "home_runs" in market or "hits" in market or "total_bases" in market:
        return "over"
    return raw or "na"


def _duplicate_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        _clean(row.get("player")).lower(),
        _clean(row.get("baseMarket") or row.get("market") or row.get("originalMarket")).lower(),
        _clean(row.get("line")),
        _normal_direction(row),
        _clean(row.get("date")),
    )


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def validate_slate(date_label: str, season: int) -> dict[str, Any]:
    warnings: list[str] = []
    prop_file = ROOT / "data" / "odds" / f"propline_props_{date_label}.csv"
    playerboard_file = ROOT / "data" / "playerboard" / f"playerboard_{season}.csv"

    prop_rows = _read_rows(prop_file)
    board_rows_all = _read_rows(playerboard_file)
    board_rows = [row for row in board_rows_all if _clean(row.get("date")) == date_label]

    if not prop_rows:
        warnings.append(f"No canonical PropLine rows found at {prop_file}.")
    if not board_rows:
        warnings.append(f"No Playerboard rows found for {date_label} in {playerboard_file}.")

    market_counts = Counter(_clean(row.get("baseMarket") or row.get("market") or row.get("originalMarket")) for row in board_rows)
    duplicate_counts = Counter(_duplicate_key(row) for row in board_rows)
    duplicates = [key for key, count in duplicate_counts.items() if count > 1 and key[0] and key[1] and key[4]]
    if duplicates:
        warnings.append(f"Found {len(duplicates)} duplicate player/market/line/direction groups after dedupe.")

    books_merged = sum(1 for row in board_rows if _positive_int(row.get("bookCount")) > 1)
    hit_rate_rows = sum(1 for row in board_rows if _clean(row.get("hitRates")))
    recent_game_rows = sum(1 for row in board_rows if _clean(row.get("recentGames")))

    status = "ok" if prop_rows and board_rows and not duplicates else "partial"
    return {
        "status": status,
        "ok": status == "ok",
        "date": date_label,
        "season": season,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "propFile": str(prop_file),
        "playerboardFile": str(playerboard_file),
        "propRows": len(prop_rows),
        "playerboardRowsForDate": len(board_rows),
        "marketsPresent": dict(sorted((key, value) for key, value in market_counts.items() if key)),
        "duplicateGroupCount": len(duplicates),
        "duplicateSamples": [list(item) for item in duplicates[:10]],
        "rowsWithMergedBooks": books_merged,
        "rowsWithHitRates": hit_rate_rows,
        "rowsWithRecentGames": recent_game_rows,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a refreshed Outlier slate before opening or deploying the UI.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    payload = validate_slate(args.date, args.season)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    raise SystemExit(0 if payload["ok"] or not args.strict else 1)


if __name__ == "__main__":
    main()
