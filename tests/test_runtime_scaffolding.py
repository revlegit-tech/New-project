from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_start_wrapper_exists_and_has_expected_parameters() -> None:
    text = (ROOT / "scripts" / "start_mlb_app.ps1").read_text(encoding="utf-8")
    for token in ["$Port = 8765", '$Host = "127.0.0.1"', "$SkipBootstrap", "$NoBrowser", '$Date = "today"']:
        assert token in text
    assert "mlb_app.asgi:app" in text
    assert "-m uvicorn" in text


def test_dockerfile_and_env_example_are_runtime_safe() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.production.example").read_text(encoding="utf-8")

    assert "mlb_app.asgi:app" in dockerfile
    assert "daily_ml_workflow.py --launch-mode" not in dockerfile
    assert "your-" not in env_example.lower()
    assert "sk-" not in env_example
    assert "DATABASE_URL=postgresql://mlb_app:replace-with-secure-password@postgres:5432/mlb_app" in env_example


def test_generated_status_files_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "data/status/" in gitignore
    assert "data/" in dockerignore
