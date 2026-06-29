from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CATEGORIES = {
    "odds snapshots": ["data/warehouse/odds_snapshots", "data/odds"],
    "normalized odds": ["data/warehouse/normalized"],
    "feature matrices": ["data/features", "data/warehouse/features"],
    "playerboard snapshots": ["data/playerboard", "data/edge_board"],
    "model artifacts": ["data/models"],
    "reports": ["data/reports", "data/audit"],
    "logs": ["data/warehouse/logs", "data/health"],
    "repair backups/temp files": ["data/tmp", "data/repair_backups", "workflow-artifacts"],
}


def build_report(*, root: Path = ROOT, keep_days: int = 30, execute: bool = False) -> dict[str, Any]:
    root = root.resolve()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, keep_days))
    allowed_roots = _allowed_roots(root)
    active = _active_artifacts(root)
    candidates: list[str] = []
    deleted: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []

    for allowed in allowed_roots:
        if not allowed.exists():
            continue
        for path in allowed.rglob("*"):
            if not path.is_file():
                continue
            if path in active:
                skipped.append(_rel(path, root))
                continue
            if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) >= cutoff:
                continue
            candidates.append(_rel(path, root))
            if execute:
                try:
                    path.unlink()
                    deleted.append(_rel(path, root))
                except OSError as error:
                    warnings.append(f"Could not delete {_rel(path, root)}: {error}")

    return {
        "dryRun": not execute,
        "keepDays": keep_days,
        "candidates": candidates,
        "deleted": deleted,
        "skipped": skipped,
        "warnings": warnings,
        "allowedRoots": [_rel(path, root) for path in allowed_roots],
    }


def _allowed_roots(root: Path) -> list[Path]:
    roots: list[Path] = []
    for paths in CATEGORIES.values():
        for item in paths:
            candidate = (root / item).resolve()
            if root in candidate.parents or candidate == root:
                roots.append(candidate)
    return roots


def _active_artifacts(root: Path) -> set[Path]:
    active: set[Path] = set()
    for pattern in (
        "data/playerboard/playerboard_*.csv",
        "data/features/prop_features_*.csv",
        "data/models/**/model.*",
    ):
        matches = sorted((path for path in root.glob(pattern) if path.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
        if matches:
            active.add(matches[0].resolve())
    return active


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune old generated MLB app artifacts. Dry-run is the default.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    report = build_report(root=Path(args.root), keep_days=args.keep_days, execute=bool(args.execute))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
