from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.ml_feature_export_service import DEFAULT_SOURCE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Sprint 13D safe player-prop outcome labels.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--season", type=int, default=0, help="MLB season. Defaults to configured current season.")
    parser.add_argument("--source", choices=("playerboard", "edge-board", "both"), default=DEFAULT_SOURCE)
    parser.add_argument("--format", choices=("csv", "json", "both"), default="both")
    parser.add_argument("--dry-run", action="store_true", help="Build and validate labels without writing files.")
    parser.add_argument("--include-ungraded", action="store_true", help="Keep missing/unsupported labels in the output artifact.")
    parser.add_argument("--output-dir", default="data/warehouse/ml_labels", help="Output directory for generated label artifacts.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(ROOT)
    container = AppContainer(settings=settings)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    manifest = container.player_prop_label_builder_service.build_labels(
        date_label=args.date,
        season=args.season or None,
        source=args.source,
        output_format=args.format,
        dry_run=args.dry_run,
        include_ungraded=args.include_ungraded,
        output_dir=output_dir,
    )
    if args.dry_run:
        _print_dry_run(manifest)
    else:
        _write_season_copy(manifest, output_dir, args.season or settings.current_season)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def _print_dry_run(manifest: dict[str, object]) -> None:
    print("Player prop label dry run")
    print(f"  date: {manifest.get('date')}")
    print(f"  source: {manifest.get('source')}")
    print(f"  row count: {manifest.get('row_count')}")
    print(f"  graded: {manifest.get('graded_count')}")
    print(f"  ungraded: {manifest.get('ungraded_count')}")
    print(f"  status counts: {json.dumps(manifest.get('status_counts') or {}, sort_keys=True)}")
    print(f"  market counts: {json.dumps(manifest.get('market_counts') or {}, sort_keys=True)}")
    print("  output paths:")
    for key, value in (manifest.get("output_paths") or {}).items():  # type: ignore[union-attr]
        print(f"    {key}: {value}")
    warnings = manifest.get("warnings") or []
    if warnings:
        print("  warnings:")
        for warning in warnings:  # type: ignore[union-attr]
            print(f"    - {warning}")


def _write_season_copy(manifest: dict[str, object], output_dir: Path, season: int) -> None:
    output_paths = manifest.get("output_paths") if isinstance(manifest.get("output_paths"), dict) else {}
    csv_display = str(output_paths.get("csv") or "")
    source = ROOT / csv_display if csv_display else output_dir / f"player_prop_labels_{manifest.get('date')}.csv"
    if not source.is_file():
        return
    target = ROOT / "data" / "training" / f"player_prop_labels_{season}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
        fieldnames = list(rows[0].keys()) if rows else []
    if not fieldnames:
        return
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    manifest.setdefault("output_paths", {})["season_csv"] = str(target.relative_to(ROOT)).replace("\\", "/")  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
