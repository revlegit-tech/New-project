from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

THIRD_PARTY = {
    "anyio",
    "fastapi",
    "pydantic",
    "requests",
    "starlette",
    "uvicorn",
}
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _root_modules(root: Path) -> set[str]:
    return {path.stem for path in root.glob("*.py")}


def _imported_base_names(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    tree = ast.parse(text)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level == 0:
                names.add(node.module.split(".", 1)[0])
    return names


def find_violations(root: Path) -> dict[Path, list[str]]:
    root_level_modules = _root_modules(root)
    stdlib = set(sys.stdlib_module_names)
    allowed = stdlib | THIRD_PARTY | {"mlb_app"}
    violations: dict[Path, list[str]] = {}
    for path in (root / "mlb_app").rglob("*.py"):
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        imported = _imported_base_names(path)
        bad = sorted(name for name in imported if name in root_level_modules and name not in allowed)
        if bad:
            violations[rel] = bad
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate mlb_app package boundary: mlb_app must not import root scripts.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    violations = find_violations(root)
    if violations:
        print("mlb_app imports root-level operational modules:", file=sys.stderr)
        for path, names in violations.items():
            print(f"  {path}: {', '.join(names)}", file=sys.stderr)
        return 1
    print("Import-boundary guard OK: mlb_app imports no root-level operational modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
