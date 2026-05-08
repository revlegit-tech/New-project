from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime paths and safety flags for the modular backend.

    The legacy entrypoint is still ``app.py``. This settings object gives new
    route/service modules a single, testable source of path configuration while
    keeping endpoint behavior stable during the migration.
    """

    root_dir: Path
    public_dir: Path
    data_dir: Path
    model_dir: Path
    model_registry_path: Path
    allow_generic_prop_model_fallback: bool = False
    research_mode_default: bool = True

    @classmethod
    def from_env(cls, root_dir: str | Path | None = None) -> "Settings":
        root = Path(root_dir or os.environ.get("MLB_APP_ROOT", ".")).resolve()
        data_dir = Path(os.environ.get("MLB_DATA_DIR", root / "data")).resolve()
        model_dir = Path(os.environ.get("MLB_MODEL_DIR", data_dir / "models")).resolve()
        registry_path = Path(
            os.environ.get("MLB_MODEL_REGISTRY", model_dir / "model_registry.json")
        ).resolve()
        allow_generic = os.environ.get("MLB_ALLOW_GENERIC_PROP_MODEL_FALLBACK", "").strip().lower()
        research_mode = os.environ.get("MLB_RESEARCH_MODE_DEFAULT", "1").strip().lower()
        return cls(
            root_dir=root,
            public_dir=(root / "public").resolve(),
            data_dir=data_dir,
            model_dir=model_dir,
            model_registry_path=registry_path,
            allow_generic_prop_model_fallback=allow_generic in {"1", "true", "yes", "on"},
            research_mode_default=research_mode not in {"0", "false", "no", "off"},
        )


settings = Settings.from_env(Path(__file__).resolve().parents[1])
