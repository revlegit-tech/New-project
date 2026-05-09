from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_root_app_py_is_retired() -> None:
    assert not (ROOT / "app.py").exists()


def test_makefile_has_no_legacy_runtime_target() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "run-legacy" not in makefile
    assert "python app.py" not in makefile
    assert "serve-wsgi-legacy" in makefile
    assert "mlb_app.asgi:app" in makefile
    assert "-k uvicorn.workers.UvicornWorker" in makefile


def test_dockerfile_uses_mlb_app_asgi() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "app.py" not in dockerfile
    assert "mlb_app.asgi:app" in dockerfile
    assert "uvicorn.workers.UvicornWorker" in dockerfile


def test_runtime_retirement_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "tools/validate_app_py_retirement.py", "--root", "."],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "passed" in result.stdout
