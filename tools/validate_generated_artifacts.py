from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

IGNORED_PARTS = {".git", ".venv", "node_modules", ".pytest_cache", ".ruff_cache", "workflow-artifacts"}
GENERATED_PATTERNS = (
    "data/features/*.csv",
    "data/models/**/*",
    "models/*.joblib",
    "models/*.pkl",
    "data/playerboard/playerboard_*.csv",
    "data/warehouse/ml_training/*.csv",
)


def find_generated_artifacts(root: Path) -> list[Path]:
    root = root.resolve()
    offenders: set[Path] = set()
    ignored = _git_ignored_paths(root)
    for pattern in GENERATED_PATTERNS:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if relative.as_posix() in ignored:
                continue
            offenders.add(relative)
    return sorted(offenders, key=lambda item: item.as_posix())


def _git_ignored_paths(root: Path) -> set[str]:
    if not (root / ".git").exists():
        return set()
    try:
        result = subprocess.run(
            ["git", "status", "--ignored", "--short", "--untracked-files=all", "--", "data", "models"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    ignored: set[str] = set()
    for line in result.stdout.splitlines():
        if line.startswith("!! "):
            ignored.add(line[3:].strip().replace("\\", "/"))
    return ignored


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail when generated data/model artifacts are present in the source tree.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    offenders = find_generated_artifacts(Path(args.root))
    if offenders:
        for offender in offenders:
            print(offender.as_posix())
        raise SystemExit(1)
    print("No generated data/model artifacts found in guarded paths.")


if __name__ == "__main__":
    main()
