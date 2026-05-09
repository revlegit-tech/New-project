from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROUTE_DIR = Path("mlb_app/api/routes")
FORBIDDEN_CALLS = {
    "build_container",
    "AppContainer",
    "AppStatusService",
    "EdgeBoardService",
    "PlayerboardService",
    "PropDetailService",
    "ModelCardService",
    "PicksService",
    "BankrollService",
    "PredictionAuditService",
    "ProplinePropsService",
}


def find_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in (root / ROUTE_DIR).glob("*.py"):
        if path.name in {"__init__.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in FORBIDDEN_CALLS:
                    violations.append(f"{path.relative_to(root)}:{node.lineno} constructs {name}; use AppContainer dependencies instead")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate native FastAPI routes use AppContainer DI and do not construct services.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    violations = find_violations(root)
    if violations:
        print("Native route DI violations:", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        return 1
    print("Native DI guard OK: routes do not construct containers/services directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
