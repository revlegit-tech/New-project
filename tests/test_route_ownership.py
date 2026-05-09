from __future__ import annotations

import ast
from pathlib import Path

from mlb_app.api.route_ownership import NATIVE_OWNED_ROUTES, ROUTE_OWNERSHIP, TEMPORARY_LEGACY_ROUTES
from mlb_app.asgi import app


def _legacy_routes() -> set[tuple[str, str]]:
    tree = ast.parse(Path("mlb_app/server.py").read_text(encoding="utf-8"))
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "add"):
            continue
        if len(node.args) < 2:
            continue
        method_node, path_node = node.args[0], node.args[1]
        if isinstance(method_node, ast.Constant) and isinstance(path_node, ast.Constant):
            routes.add((str(method_node.value).upper(), str(path_node.value)))
    return routes


def test_fastapi_owned_routes_are_not_registered_in_legacy_router() -> None:
    legacy_routes = _legacy_routes()
    assert not (legacy_routes & NATIVE_OWNED_ROUTES)
    assert legacy_routes <= TEMPORARY_LEGACY_ROUTES


def test_route_ownership_matrix_matches_fastapi_route_names() -> None:
    route_names = {getattr(route, "name", "") for route in app.routes}
    missing = [entry.native_route_name for entry in ROUTE_OWNERSHIP if entry.owner == "FastAPI" and entry.native_route_name not in route_names]
    assert missing == []
