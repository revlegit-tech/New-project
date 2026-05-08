from __future__ import annotations

"""Phase 21 freshness report for the MLB app data pipeline."""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AUDIT_DIR = DATA / "warehouse" / "audits"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def file_status(label: str, path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        return {
            "label": label,
            "path": str(path),
            "exists": False,
            "required": required,
            "status": "missing" if required else "optional_missing",
        }
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - modified).total_seconds())
    return {
        "label": label,
        "path": str(path),
        "exists": True,
        "required": required,
        "status": "ok",
        "sizeBytes": stat.st_size,
        "modifiedAt": modified.isoformat(),
        "ageSeconds": round(age_seconds, 3),
    }


def non_empty_count(rows: list[dict[str, Any]], field: str) -> int:
    return sum(1 for row in rows if clean(row.get(field)))


def coverage(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    total = len(rows)
    items = []
    for field in fields:
        count = non_empty_count(rows, field)
        items.append({
            "field": field,
            "presentRows": count,
            "coverage": round(count / max(1, total), 4),
        })
    return {"rows": total, "fields": items}


def build_report(date_label: str, season: int, *, write: bool = False) -> dict[str, Any]:
    files = [
        file_status("PropLine props", DATA / "odds" / f"propline_props_{date_label}.csv"),
        file_status("Game context", DATA / "warehouse" / "game_context" / f"game_context_{date_label}.csv"),
        file_status("Game context markets", DATA / "warehouse" / "game_context" / f"game_context_markets_{date_label}.csv"),
        file_status("Phase 18 weather", DATA / "warehouse" / "game_context" / f"weather_phase18_{date_label}.json"),
        file_status("Line movement snapshots", DATA / "warehouse" / "game_context" / "line_snapshots" / f"game_line_snapshots_{date_label}.csv", required=False),
        file_status("Playerboard", DATA / "playerboard" / f"playerboard_{season}.csv"),
        file_status("Phase 17 context audit", DATA / "warehouse" / "audits" / f"phase17_game_context_audit_{season}_{date_label}.json", required=False),
        file_status("Phase 21 daily report", DATA / "warehouse" / "audits" / f"phase21_daily_refresh_{date_label}_morning.json", required=False),
    ]

    context_path = DATA / "warehouse" / "game_context" / f"game_context_{date_label}.csv"
    context_rows = read_csv(context_path)
    context_coverage = coverage(context_rows, [
        "team_moneyline",
        "opponent_moneyline",
        "game_total",
        "moneyline_implied_probability",
        "team_implied_runs",
        "opponent_implied_runs",
        "weather_temperature_f",
        "weather_wind_mph",
        "weather_humidity",
        "weather_wind_direction",
        "roof_status",
        "open_team_moneyline",
        "moneyline_move",
        "open_game_total",
        "total_move",
    ])

    playerboard_rows = [
        row for row in read_csv(DATA / "playerboard" / f"playerboard_{season}.csv")
        if clean(row.get("date")) == date_label
    ]
    playerboard_coverage = coverage(playerboard_rows, [
        "player",
        "market",
        "team",
        "opponent",
        "american_odds",
        "sportsbook_count",
        "best_book",
        "team_moneyline",
        "game_total",
        "team_implied_runs",
        "weather_temperature_f",
    ])

    missing_required = [item for item in files if item["required"] and not item["exists"]]
    critical_context_missing = [
        item["field"] for item in context_coverage["fields"]
        if item["field"] in {
            "team_moneyline",
            "opponent_moneyline",
            "game_total",
            "team_implied_runs",
            "opponent_implied_runs",
            "weather_temperature_f",
            "weather_wind_mph",
        }
        and item["coverage"] == 0
    ]

    movement_status = "ready"
    movement_fields = {"open_team_moneyline", "moneyline_move", "open_game_total", "total_move"}
    if any(item["field"] in movement_fields and item["coverage"] == 0 for item in context_coverage["fields"]):
        movement_status = "pending_or_single_snapshot"

    report = {
        "status": "ok" if not missing_required and not critical_context_missing else "warning",
        "date": date_label,
        "season": season,
        "generatedAt": now_iso(),
        "files": files,
        "contextCoverage": context_coverage,
        "playerboardCoverage": playerboard_coverage,
        "movementStatus": movement_status,
        "missingRequiredFiles": [item["label"] for item in missing_required],
        "criticalContextMissing": critical_context_missing,
        "notes": [
            "Opening-line movement can remain pending until multiple same-day snapshots or an opening-line provider are available.",
            "OddsPapi is optional for Phase 21; PropLine/Open-Meteo/local references drive current game context.",
        ],
    }
    if write:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        (AUDIT_DIR / f"phase21_freshness_{date_label}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 21 data freshness report.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_report(args.date, args.season, write=args.write), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
