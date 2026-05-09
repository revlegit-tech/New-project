from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


def _registered_legacy_routes(server_path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(server_path.read_text(encoding="utf-8"))
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add"):
            continue
        if len(node.args) < 2:
            continue
        method_node, path_node = node.args[0], node.args[1]
        if isinstance(method_node, ast.Constant) and isinstance(path_node, ast.Constant):
            routes.add((str(method_node.value).upper(), str(path_node.value)))
    return routes


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Sprint 2 route ownership boundaries.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root))

    from mlb_app.api.route_ownership import NATIVE_OWNED_ROUTES, ROUTE_OWNERSHIP, TEMPORARY_LEGACY_ROUTES
    from mlb_app.asgi import app

    legacy_routes = _registered_legacy_routes(root / "mlb_app" / "server.py")
    duplicate_native = sorted(NATIVE_OWNED_ROUTES & legacy_routes)
    unexpected_legacy = sorted(legacy_routes - TEMPORARY_LEGACY_ROUTES)

    route_names = {getattr(route, "name", "") for route in getattr(app, "routes", [])}
    missing_native = sorted(
        entry.native_route_name
        for entry in ROUTE_OWNERSHIP
        if entry.owner == "FastAPI" and entry.native_route_name not in route_names
    )

    errors: list[str] = []
    if duplicate_native:
        errors.append(f"FastAPI-owned routes registered in legacy router: {duplicate_native}")
    if unexpected_legacy:
        errors.append(f"Legacy router has routes not listed as temporary fallback: {unexpected_legacy}")
    if missing_native:
        errors.append(f"FastAPI route names missing from ASGI app: {missing_native}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"Route ownership OK: {len(NATIVE_OWNED_ROUTES)} native-owned, {len(TEMPORARY_LEGACY_ROUTES)} temporary legacy fallback.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
