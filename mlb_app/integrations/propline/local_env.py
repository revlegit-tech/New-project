from __future__ import annotations

import os
from pathlib import Path


def load_local_env(path: str | Path = ".env", override: bool = False) -> dict[str, str]:
    """Load KEY=VALUE pairs from a local .env file into os.environ.

    This intentionally avoids an extra dependency like python-dotenv.
    Existing environment variables are preserved unless override=True.
    """
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = Path(__file__).resolve().parents[3] / env_path
    if not env_path.exists():
        return {}

    loaded: dict[str, str] = {}

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")

        if not key:
            continue

        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value

    return loaded
