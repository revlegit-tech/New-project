from __future__ import annotations

"""Clean generated backup artifacts that must not live in source control.

This utility is intentionally conservative: by default it only removes generated
backup/header-mismatch files older than 24 hours. Use ``--dry-run`` in CI or
before collector changes to verify that new generated files will not pollute git
status.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_PATTERNS = (
    "data/playerboard/*.header_mismatch_*.csv",
    "data/**/*.backup*",
    "data/**/*.phase*_backup*",
    "data/**/*.tmp",
    "public/*.backup*",
    "public/**/*.backup*",
    "mlb_app/**/*.backup*",
    "mlb_app/**/*.phase*_backup*",
)


@dataclass(frozen=True)
class CleanupCandidate:
    path: Path
    age_hours: float


def _age_hours(path: Path, now: datetime) -> float:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (now - modified).total_seconds() / 3600)


def iter_candidates(root: Path, *, older_than_hours: float, patterns: tuple[str, ...] = DEFAULT_PATTERNS) -> list[CleanupCandidate]:
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=max(0.0, older_than_hours))
    candidates: list[CleanupCandidate] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified <= threshold:
                candidates.append(CleanupCandidate(path=path, age_hours=_age_hours(path, now)))
                seen.add(resolved)
    return sorted(candidates, key=lambda item: str(item.path))


def cleanup(root: Path, *, older_than_hours: float = 24.0, dry_run: bool = True) -> int:
    candidates = iter_candidates(root, older_than_hours=older_than_hours)
    for candidate in candidates:
        action = "would remove" if dry_run else "removed"
        print(f"{action}: {candidate.path} ({candidate.age_hours:.1f}h old)")
        if not dry_run:
            candidate.path.unlink(missing_ok=True)
    return len(candidates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove generated MLB app backup files older than a retention window.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root. Defaults to the current directory.")
    parser.add_argument("--older-than-hours", type=float, default=24.0, help="Retention window in hours. Defaults to 24.")
    parser.add_argument("--dry-run", action="store_true", help="Print files without deleting them.")
    parser.add_argument("--delete", action="store_true", help="Delete matching files. Required for mutation.")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    dry_run = not args.delete or args.dry_run
    count = cleanup(root, older_than_hours=args.older_than_hours, dry_run=dry_run)
    print(f"matched={count} dryRun={dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
