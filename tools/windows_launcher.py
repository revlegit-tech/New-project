from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


APP_URL = "http://127.0.0.1:8765"


def message(title: str, body: str) -> None:
    print(f"{title}: {body}")
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, body, title, 0x10)
    except Exception:
        pass


def find_repo_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / "scripts" / "start_mlb_app.ps1").exists():
            return candidate
    return None


def main() -> int:
    if getattr(sys, "frozen", False):
        start = Path(sys.executable).resolve().parent
    else:
        start = Path(__file__).resolve().parent

    root = find_repo_root(start)
    if root is None:
        message(
            "MLB Launcher Error",
            "Could not find scripts\\start_mlb_app.ps1. Keep the launcher inside this repo or inside its dist folder.",
        )
        return 1

    script = root / "scripts" / "start_mlb_app.ps1"
    python_exe = root / ".venv" / "Scripts" / "python.exe"

    if not python_exe.exists():
        message(
            "MLB Launcher Error",
            f"Could not find .venv\\Scripts\\python.exe under:\n{root}\n\nRebuild the venv before launching.",
        )
        return 1

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(root))
    env.setdefault("BASEBALL_PROP_APP_URL", APP_URL)

    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=str(root),
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except Exception as exc:
        message("MLB Launcher Error", f"Failed to start app:\n{exc}")
        return 1

    time.sleep(3)
    webbrowser.open(APP_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
