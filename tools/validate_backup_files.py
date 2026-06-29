from __future__ import annotations

import argparse
from pathlib import Path

IGNORED_PARTS = {".git", ".venv", "node_modules", ".pytest_cache", ".pytest_tmp", ".ruff_cache", "workflow-artifacts"}
BACKUP_MARKERS = (
    ".backup_",
    ".phasebackup",
    "_phasebackup",
    ".phase19_backup_",
    ".phase20_backup_",
    ".phase20v2_backup_",
    ".phase20v3_backup_",
    ".phase21_backup",
    ".phase21v2_backup_",
    ".phase22_backup_",
    ".phase22v2_backup_",
)


def iter_backup_files(root: Path) -> list[Path]:
    root = root.resolve()
    offenders: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        name = path.name.lower()
        if any(marker in name for marker in BACKUP_MARKERS):
            offenders.append(relative)
    return sorted(offenders, key=lambda item: item.as_posix())


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail when source-tree backup files are present.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    offenders = iter_backup_files(Path(args.root))
    if offenders:
        for offender in offenders:
            print(offender.as_posix())
        raise SystemExit(1)
    print("No source-tree backup files found.")


if __name__ == "__main__":
    main()
