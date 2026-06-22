from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Export safe Sprint 13C player-prop ML feature rows.")
    parser.add_argument("--date", default="", help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--season", type=int, default=0, help="MLB season. Defaults to configured current season.")
    parser.add_argument("--source", choices=("playerboard", "edge-board", "both"), default=DEFAULT_SOURCE)
    parser.add_argument("--format", choices=("csv", "json", "both"), default="both")
    parser.add_argument("--dry-run", action="store_true", help="Build and validate rows without writing files.")
    parser.add_argument("--output-dir", default="data/warehouse/ml_features", help="Output directory for generated exports.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(ROOT)
    container = AppContainer(settings=settings)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    manifest = container.ml_feature_export_service.export(
        date_label=args.date,
        season=args.season or None,
        source=args.source,
        output_format=args.format,
        dry_run=args.dry_run,
        output_dir=output_dir,
    )
    if args.dry_run:
        _print_dry_run(manifest)
    else:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def _print_dry_run(manifest: dict[str, object]) -> None:
    print("ML feature export dry run")
    print(f"  date: {manifest.get('date')}")
    print(f"  source: {manifest.get('source')}")
    print(f"  row count: {manifest.get('row_count')}")
    print(f"  market counts: {json.dumps(manifest.get('market_counts') or {}, sort_keys=True)}")
    print(f"  safe feature count: {manifest.get('safe_feature_count')}")
    print(f"  blocked leakage fields count: {manifest.get('leakage_blocked_field_count')}")
    print(f"  game-market matches: {manifest.get('game_market_match_count')}")
    print(f"  game-market missing: {manifest.get('game_market_missing_count')}")
    print("  output paths:")
    for key, value in (manifest.get("output_paths") or {}).items():  # type: ignore[union-attr]
        print(f"    {key}: {value}")
    warnings = manifest.get("warnings") or []
    if warnings:
        print("  warnings:")
        for warning in warnings:  # type: ignore[union-attr]
            print(f"    - {warning}")


if __name__ == "__main__":
    raise SystemExit(main())
