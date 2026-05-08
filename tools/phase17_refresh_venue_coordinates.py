"""Phase 17 v5: refresh canonical MLB venue coordinates for Open-Meteo weather.

This tool merges the repo's canonical coordinate CSV into compatibility files used by
older Phase 17 scripts. It never fetches network data and never fabricates missing
coordinates.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "data" / "reference" / "mlb_venue_coordinates.csv"
COMPAT_PATHS = [
    ROOT / "data" / "reference" / "venue_coordinates.csv",
    ROOT / "data" / "reference" / "stadium_coordinates.csv",
]
AUDIT_DIR = ROOT / "data" / "warehouse" / "audits"

REQUIRED_FIELDS = ["team", "venue", "venue_aliases", "latitude", "longitude", "coordinate_source"]


def _norm(value: object) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def write_rows(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in REQUIRED_FIELDS})


def validate_rows(rows: list[dict[str, str]]) -> list[str]:
    problems: list[str] = []
    seen_venues: set[str] = set()
    for idx, row in enumerate(rows, start=2):
        venue = row.get("venue", "").strip()
        team = row.get("team", "").strip()
        if not team:
            problems.append(f"row {idx}: missing team")
        if not venue:
            problems.append(f"row {idx}: missing venue")
        try:
            lat = float(row.get("latitude", ""))
            lon = float(row.get("longitude", ""))
        except ValueError:
            problems.append(f"row {idx}: invalid latitude/longitude for {venue or team}")
            continue
        if not (-90 <= lat <= 90):
            problems.append(f"row {idx}: latitude out of range for {venue}: {lat}")
        if not (-180 <= lon <= 180):
            problems.append(f"row {idx}: longitude out of range for {venue}: {lon}")
        key = _norm(venue)
        if key in seen_venues:
            problems.append(f"row {idx}: duplicate venue {venue}")
        seen_venues.add(key)
    return problems


def merge_rows(base_rows: list[dict[str, str]], incoming_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for row in base_rows:
        key = _norm(row.get("venue")) or _norm(row.get("team"))
        if key:
            merged[key] = {field: row.get(field, "") for field in REQUIRED_FIELDS}
    for row in incoming_rows:
        key = _norm(row.get("venue")) or _norm(row.get("team"))
        if key:
            merged[key] = {field: row.get(field, "") for field in REQUIRED_FIELDS}
    return sorted(merged.values(), key=lambda item: (item.get("team", ""), item.get("venue", "")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh MLB venue coordinate reference files.")
    parser.add_argument("--write", action="store_true", help="Write compatibility coordinate files.")
    parser.add_argument("--source", type=Path, default=CANONICAL_PATH, help="Canonical coordinate CSV to merge from.")
    args = parser.parse_args()

    incoming_rows = read_rows(args.source)
    problems = validate_rows(incoming_rows)
    if problems:
        print(json.dumps({"status": "error", "problems": problems}, indent=2))
        raise SystemExit(1)

    results = []
    for compat_path in COMPAT_PATHS:
        existing_rows = read_rows(compat_path)
        merged_rows = merge_rows(existing_rows, incoming_rows)
        if args.write:
            write_rows(compat_path, merged_rows)
        results.append(
            {
                "path": str(compat_path),
                "existingRows": len(existing_rows),
                "incomingRows": len(incoming_rows),
                "mergedRows": len(merged_rows),
                "written": bool(args.write),
            }
        )

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit = {
        "status": "ok",
        "canonicalPath": str(args.source),
        "canonicalRows": len(incoming_rows),
        "written": bool(args.write),
        "results": results,
        "venues": [row.get("venue", "") for row in incoming_rows],
    }
    if args.write:
        (AUDIT_DIR / "phase17_v5_venue_coordinates.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
