from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        db_path=data_dir / "state.sqlite3",
        current_season=2026,
    )


def test_health_and_status_routes_return_safe_missing_status(tmp_path: Path) -> None:
    client = TestClient(create_app(container=AppContainer(settings=make_settings(tmp_path))), client=("127.0.0.1", 50000))

    for path in ["/api/health", "/api/runtime/status", "/api/workflow/status", "/api/data-freshness?date=2026-06-23"]:
        response = client.get(path)
        assert response.status_code == 200
        text = json.dumps(response.json())
        assert "C:\\Users\\" not in text
        assert "/mnt/data" not in text
        assert str(tmp_path) not in text


def test_runtime_status_sanitizes_status_file_contents(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    status_dir = settings.data_dir / "status"
    status_dir.mkdir(parents=True)
    (status_dir / "runtime_status.json").write_text(
        json.dumps({"status": "success", "secretToken": "abc", "path": r"C:\Users\RevLe\secret.txt"}),
        encoding="utf-8",
    )
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    payload = client.get("/api/runtime/status").json()
    text = json.dumps(payload)
    assert "abc" not in text
    assert "C:\\Users\\" not in text
    assert payload["runtime"]["secretToken"] == "[redacted]"
