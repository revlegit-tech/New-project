from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def row_key(row: dict[str, Any]) -> tuple[str, ...]:
    preferred = [
        "date",
        "player",
        "team",
        "opponent",
        "market",
        "side",
        "line",
        "book",
        "americanOdds",
        "gameTime",
    ]
    return tuple(str(row.get(key) or "").strip() for key in preferred)


def load_best_artifacts(scan_file: Path) -> dict[str, dict[str, Any]]:
    best_by_date: dict[str, dict[str, Any]] = {}
    with scan_file.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            run_label = str(row.get("run_label") or "")
            run_date = run_label[:10]
            file_path = Path(str(row.get("file") or ""))
            try:
                rows = int(row.get("rows", 0) or 0)
            except ValueError:
                rows = 0
            if not run_date or not file_path.exists():
                continue
            current = best_by_date.get(run_date)
            if current is None or rows > current["rows"]:
                best_by_date[run_date] = {
                    "run_date": run_date,
                    "rows": rows,
                    "file": file_path,
                    "run_label": run_label,
                }
    return best_by_date


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely merge recovered artifact playerboards into the live playerboard.")
    parser.add_argument("--scan", default="data/health/artifact_playerboard_market_scan.csv", help="Scan manifest from scan_artifact_playerboards.py.")
    parser.add_argument("--target", default="data/playerboard/playerboard_2026.csv", help="Live playerboard CSV to update.")
    parser.add_argument("--report", default="data/health/artifact_playerboard_merge_report.csv", help="Merge report CSV output path.")
    parser.add_argument("--backup-dir", default="data/backups", help="Backup directory used before --apply writes.")
    parser.add_argument("--apply", action="store_true", help="Actually write the merged target. Default is dry-run.")
    args = parser.parse_args()

    scan_file = Path(args.scan)
    target_file = Path(args.target)
    report_file = Path(args.report)
    backup_dir = Path(args.backup_dir)
    report_file.parent.mkdir(parents=True, exist_ok=True)

    if not scan_file.exists():
        print(f"Missing scan file; nothing to merge: {scan_file}")
        _write_report(report_file, [])
        return 0

    if not target_file.exists():
        print(f"Missing local playerboard; merge skipped: {target_file}")
        _write_report(report_file, [])
        return 1 if args.apply else 0

    best_by_date = load_best_artifacts(scan_file)
    local_fields, local_rows = read_csv_rows(target_file)
    if not local_fields:
        print(f"Local playerboard has no header fields; merge skipped: {target_file}")
        _write_report(report_file, [])
        return 1

    artifact_rows: list[dict[str, str]] = []
    merge_report: list[dict[str, Any]] = []
    for run_date, info in sorted(best_by_date.items()):
        artifact_fields, rows = read_csv_rows(Path(info["file"]))
        selected = [row for row in rows if row.get("date") == run_date]
        skipped_other_dates = len(rows) - len(selected)
        artifact_rows.extend(selected)
        merge_report.append({
            "run_date": run_date,
            "run_label": info["run_label"],
            "source_file": str(info["file"]),
            "source_rows_total": info["rows"],
            "selected_rows_for_date": len(selected),
            "skipped_other_dates": skipped_other_dates,
            "source_field_count": len(artifact_fields),
        })

    fieldnames = list(local_fields)
    for row in artifact_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    combined_by_key = {row_key(row): row for row in local_rows}
    added = 0
    replaced = 0
    for row in artifact_rows:
        key = row_key(row)
        if key in combined_by_key:
            replaced += 1
        else:
            added += 1
        combined_by_key[key] = row
    combined_rows = list(combined_by_key.values())

    backup_file = ""
    if args.apply:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"{target_file.stem}_before_artifact_merge_{stamp}{target_file.suffix}"
        shutil.copy2(target_file, backup_path)
        backup_file = str(backup_path)
        with target_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in combined_rows:
                writer.writerow(row)

    for row in merge_report:
        row.update({
            "mode": "apply" if args.apply else "dry_run",
            "local_rows_before": len(local_rows),
            "artifact_rows_selected_total": len(artifact_rows),
            "rows_added": added,
            "rows_replaced_or_deduped": replaced,
            "rows_after": len(combined_rows),
            "backup_file": backup_file,
        })
    _write_report(report_file, merge_report)

    print("MERGE DRY-RUN COMPLETE" if not args.apply else "MERGE APPLIED")
    print(f"Local rows before: {len(local_rows)}")
    print(f"Artifact rows selected: {len(artifact_rows)}")
    print(f"Rows added: {added}")
    print(f"Rows replaced/deduped: {replaced}")
    print(f"Rows after: {len(combined_rows)}")
    if args.apply:
        print(f"Backup: {backup_file}")
        print(f"Updated playerboard: {target_file}")
    else:
        print("No live files were changed. Re-run with --apply to write after reviewing the report.")
    print(f"Merge report: {report_file}")
    return 0


def _write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_date",
        "run_label",
        "source_file",
        "source_rows_total",
        "selected_rows_for_date",
        "skipped_other_dates",
        "source_field_count",
        "mode",
        "local_rows_before",
        "artifact_rows_selected_total",
        "rows_added",
        "rows_replaced_or_deduped",
        "rows_after",
        "backup_file",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
