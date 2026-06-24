from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def test_scheduler_setup_uses_project_virtualenv_python() -> None:
    source = _source("setup_3x_daily_collector.ps1")

    assert 'Join-Path $Project ".venv\\Scripts\\python.exe"' in source
    assert "Missing project virtualenv Python" in source
    assert "$env:PYTHONPATH = $Project" in source
    assert "AppData\\Local\\Programs\\Python\\Python312\\python.exe" not in source


def test_start_script_uses_project_virtualenv_and_asgi_entrypoint() -> None:
    source = _source("scripts/start_mlb_app.ps1")

    assert 'Join-Path $Root ".venv\\Scripts\\python.exe"' in source
    assert "mlb_app.asgi:app" in source
    assert "-m uvicorn" in source

def test_windows_launcher_delegates_to_project_start_script() -> None:
    source = _source("tools/windows_launcher.py")

    assert 'root / "scripts" / "start_mlb_app.ps1"' in source
    assert 'root / ".venv" / "Scripts" / "python.exe"' in source
    assert "subprocess.Popen" in source
    assert "AppData\\Local\\Programs\\Python" not in source

