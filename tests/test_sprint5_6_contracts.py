from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.asgi import app
from tools.validate_backup_files import iter_backup_files
from tools.validate_import_boundaries import find_violations as find_import_boundary_violations
from tools.validate_native_di import find_violations as find_native_di_violations


def test_no_extra_allow_in_mlb_app_pydantic_models() -> None:
    offenders: list[Path] = []
    for path in Path("mlb_app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if 'extra="allow"' in text or "extra='allow'" in text:
            offenders.append(path)
    assert offenders == []


def test_sprint5_source_tree_guards_are_clean() -> None:
    root = Path(".").resolve()
    assert find_import_boundary_violations(root) == {}
    assert iter_backup_files(root) == []
    assert find_native_di_violations(root) == []


def test_native_contracts_expose_schema_versions() -> None:
    paths = [
        "/api/app/status",
        "/api/edge-board?season=2026&limit=2",
        "/api/playerboard?season=2026&limit=2",
        "/api/playerboard/health",
        "/api/prop-detail?market=batter_hits&player=Contract%20Player&team=NYY&opponent=BAL&line=0.5&americanOdds=-110",
        "/api/model-cards",
        "/api/my-picks",
        "/api/bankroll/settings",
        "/api/exposure/summary",
        "/api/prediction-events",
    ]
    with TestClient(app) as client:
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            payload = response.json()
            assert isinstance(payload.get("schemaVersion"), str), path
            assert payload["schemaVersion"], path


def test_openapi_uses_strict_native_contract_schemas() -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]
    for name in ["EdgeBoardRow", "ModelCardItem", "PickItem", "ExposureSummaryPayload", "PropDetailPayload"]:
        assert components[name]["additionalProperties"] is False


def test_openapi_operation_ids_are_unique() -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]

    assert len(operation_ids) == len(set(operation_ids))
    assert "/api/{api_path}" not in schema["paths"]
    assert "/api/{api_path:path}" not in schema["paths"]
    assert "/{static_path}" not in schema["paths"]
    assert "/{static_path:path}" not in schema["paths"]
