from __future__ import annotations

import argparse
import re
from pathlib import Path

IGNORED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    "workflow-artifacts",
}
ALLOWED_SOURCE_FILENAMES = {"validate_backup_files.py"}
BACKUP_NAME_PATTERN = re.compile(r"backup|(^|[._-])phase[^/\\]*backup", re.IGNORECASE)


def iter_backup_files(root: Path) -> list[Path]:
    root = root.resolve()
    offenders: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        name = path.name
        if name.lower() in ALLOWED_SOURCE_FILENAMES:
            continue
        if BACKUP_NAME_PATTERN.search(name):
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
