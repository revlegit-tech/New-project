#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

ALLOWED_TRACKED_FILES = {".env.example", ".env.template"}

FORBIDDEN_TRACKED_PATTERNS = (
    ".env",
    ".env.*",
    "*.env",
    ".en",
    "*.key",
    "*.pem",
    "secrets.*",
)


def matches(path: str) -> bool:
    name = Path(path).name
    if path in ALLOWED_TRACKED_FILES or name in ALLOWED_TRACKED_FILES:
        return False
    return any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern) for pattern in FORBIDDEN_TRACKED_PATTERNS)


def tracked_files() -> list[str]:
    try:
        completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def main() -> int:
    offenders = [path for path in tracked_files() if matches(path)]
    if offenders:
        print("Forbidden secret-bearing files are tracked:", file=sys.stderr)
        for path in offenders:
            print(f"  - {path}", file=sys.stderr)
        print("Run: git rm --cached <file> and rotate any exposed secret values.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
