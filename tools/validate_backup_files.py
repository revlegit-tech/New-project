from __future__ import annotations

import argparse
from pathlib import Path

BACKUP_SUFFIXES = {
    ".bak",
    ".backup",
}

BACKUP_MARKERS = (
    ".phase",
    "_backup",
    ".backup",
    ".bak",
    "header_mismatch_",
)

IGNORED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "playwright-report",
    "test-results",
}

IGNORED_FILES = {
    "tools/validate_backup_files.py",
    "tests/test_cleanup_generated_backups.py",
}


def iter_backup_files(root: Path) -> list[Path]:
    offenders: list[Path] = []
    root = root.resolve()

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(root)
        rel_posix = rel.as_posix()

        if rel_posix in IGNORED_FILES:
            continue

        if any(part in IGNORED_DIRS for part in rel.parts):
            continue

        name = path.name.lower()
        suffix = path.suffix.lower()

        if suffix in BACKUP_SUFFIXES or any(marker in name for marker in BACKUP_MARKERS):
            offenders.append(rel)

    return sorted(offenders, key=lambda p: p.as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate that generated backup files are not committed.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    offenders = iter_backup_files(Path(args.root))
    if offenders:
        print("Backup/generated files found:")
        for path in offenders:
            print(f"  {path}")
        return 1

    print("Backup file guard OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
