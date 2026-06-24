from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def test_runtime_status_exposes_live_runtime_without_absolute_paths() -> None:
    source = _source("mlb_app/services/runtime_status_service.py")

    assert "def _live_runtime_payload(settings: Settings)" in source
    assert "sys.prefix" in source
    assert "sys.executable" in source
    assert '"liveRuntime": live_runtime' in source
    assert '"isProjectVenv": is_project_venv' in source
    assert '"databaseUrlKind": _database_url_kind' in source
    assert "C:\\\\Users" not in source


def test_runtime_status_route_still_uses_runtime_status_service() -> None:
    source = _source("mlb_app/api/routes/runtime_status.py")

    assert '@router.get("/runtime/status"' in source
    assert "RuntimeStatusService(container.settings)" in source
    assert "service.runtime_status" in source
