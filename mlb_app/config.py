from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping


def active_mlb_season(today: date | None = None) -> int:
    """Return the active MLB season used when no explicit season is configured.

    MLB app data files are year-suffixed. In normal operation the active season
    is the current calendar year; tests can pass a fixed date through this helper
    without monkeypatching module globals.
    """

    today = today or date.today()
    return today.year


def _int_from_env(name: str, fallback: int, source: Mapping[str, str] | None = None) -> int:
    raw = (source or os.environ).get(name, "")
    try:
        return int(str(raw).strip()) if str(raw).strip() else fallback
    except (TypeError, ValueError):
        return fallback


@dataclass(frozen=True)
class Settings:
    """Runtime paths and safety flags for the modular backend.

    ``mlb_app`` is the canonical production runtime. This settings object gives
    route/service modules a single, testable source of path and season
    configuration while keeping endpoint behavior stable during the migration.
    """

    root_dir: Path
    public_dir: Path
    data_dir: Path
    model_dir: Path
    model_registry_path: Path
    allow_generic_prop_model_fallback: bool = False
    research_mode_default: bool = True
    current_season: int = active_mlb_season()
    db_path: Path | None = None

    @property
    def state_db_path(self) -> Path:
        """Transactional SQLite database path for app-owned mutable state."""

        return (self.db_path or (self.data_dir / "mlb_app_state.sqlite3")).resolve()

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
        season = _int_from_env("MLB_CURRENT_SEASON", active_mlb_season())
        db_path = Path(os.environ.get("MLB_APP_DB_PATH", data_dir / "mlb_app_state.sqlite3")).resolve()
        return cls(
            root_dir=root,
            public_dir=(root / "public").resolve(),
            data_dir=data_dir,
            model_dir=model_dir,
            model_registry_path=registry_path,
            allow_generic_prop_model_fallback=allow_generic in {"1", "true", "yes", "on"},
            research_mode_default=research_mode not in {"0", "false", "no", "off"},
            current_season=season,
            db_path=db_path,
        )

    def season_from_query(self, query: dict[str, list[str]] | None = None, key: str = "season") -> int:
        """Read a season query parameter with ``current_season`` as fallback."""

        values = (query or {}).get(key) or []
        raw = values[0] if values else ""
        try:
            return int(str(raw).strip()) if str(raw).strip() else self.current_season
        except (TypeError, ValueError):
            return self.current_season


settings = Settings.from_env(Path(__file__).resolve().parents[1])
