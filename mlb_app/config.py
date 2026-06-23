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


def _float_from_env(name: str, fallback: float, source: Mapping[str, str] | None = None) -> float:
    raw = (source or os.environ).get(name, "")
    try:
        return float(str(raw).strip()) if str(raw).strip() else fallback
    except (TypeError, ValueError):
        return fallback


def _bool_from_env(name: str, fallback: bool, source: Mapping[str, str] | None = None) -> bool:
    raw = (source or os.environ).get(name, "")
    if str(raw).strip() == "":
        return fallback
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_value(*names: str, source: Mapping[str, str] | None = None, fallback: str = "") -> str:
    env = source or os.environ
    for name in names:
        raw = env.get(name, "")
        if str(raw).strip():
            return str(raw).strip()
    return fallback


def _csv_tuple_from_env(name: str, fallback: tuple[str, ...], source: Mapping[str, str] | None = None) -> tuple[str, ...]:
    raw = (source or os.environ).get(name, "")
    if not str(raw).strip():
        return fallback
    return tuple(part.strip() for part in str(raw).replace("\n", ",").split(",") if part.strip())


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
    database_url: str = ""
    database_pool_size: int = 5
    database_echo: bool = False
    db_enabled: bool = False
    db_fallback_to_csv: bool = True
    game_market_enrichment_enabled: bool = True
    team_game_market_projections_enabled: bool = False
    board_cache_ttl_seconds: float = 30.0
    board_cache_max_keys: int = 256
    blocking_work_max_concurrent: int = 24
    blocking_work_timeout_seconds: float = 5.0
    edge_board_timeout_seconds: float = 5.0
    playerboard_timeout_seconds: float = 5.0
    prop_detail_timeout_seconds: float = 2.0
    model_snapshot_cache_ttl_seconds: float = 60.0
    csp_report_only: bool = False
    csp_allow_inline: bool = False
    read_rate_limit_per_minute: int = 120
    read_rate_limit_burst: int = 30
    admin_rate_limit_per_minute: int = 10
    rate_limit_max_buckets: int = 8192
    trusted_proxy_cidrs: tuple[str, ...] = ("127.0.0.1/32", "::1/128")

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
        database_url = _env_value("DATABASE_URL", "MLB_DATABASE_URL")
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
            database_url=database_url,
            database_pool_size=_int_from_env("DATABASE_POOL_SIZE", _int_from_env("MLB_DATABASE_POOL_SIZE", 5)),
            database_echo=_bool_from_env("DATABASE_ECHO", _bool_from_env("MLB_DATABASE_ECHO", False)),
            db_enabled=_bool_from_env("DB_ENABLED", _bool_from_env("MLB_DB_ENABLED", False)),
            db_fallback_to_csv=_bool_from_env("DB_FALLBACK_TO_CSV", _bool_from_env("MLB_DB_FALLBACK_TO_CSV", True)),
            game_market_enrichment_enabled=_bool_from_env(
                "GAME_MARKET_ENRICHMENT_ENABLED",
                _bool_from_env("MLB_GAME_MARKET_ENRICHMENT_ENABLED", True),
            ),
            team_game_market_projections_enabled=_bool_from_env(
                "TEAM_GAME_MARKET_PROJECTIONS_ENABLED",
                _bool_from_env("MLB_TEAM_GAME_MARKET_PROJECTIONS_ENABLED", False),
            ),
            board_cache_ttl_seconds=_float_from_env("MLB_BOARD_CACHE_TTL_SECONDS", 30.0),
            board_cache_max_keys=_int_from_env("MLB_BOARD_CACHE_MAX_KEYS", 256),
            blocking_work_max_concurrent=_int_from_env("MLB_BLOCKING_WORK_MAX_CONCURRENT", 24),
            blocking_work_timeout_seconds=_float_from_env("MLB_BLOCKING_WORK_TIMEOUT_SECONDS", 5.0),
            edge_board_timeout_seconds=_float_from_env("MLB_EDGE_BOARD_TIMEOUT_SECONDS", 5.0),
            playerboard_timeout_seconds=_float_from_env("MLB_PLAYERBOARD_TIMEOUT_SECONDS", 5.0),
            prop_detail_timeout_seconds=_float_from_env("MLB_PROP_DETAIL_TIMEOUT_SECONDS", 2.0),
            model_snapshot_cache_ttl_seconds=_float_from_env("MLB_MODEL_SNAPSHOT_CACHE_TTL_SECONDS", 60.0),
            csp_report_only=_bool_from_env("MLB_CSP_REPORT_ONLY", False),
            csp_allow_inline=_bool_from_env("MLB_CSP_ALLOW_INLINE", False),
            read_rate_limit_per_minute=_int_from_env("MLB_READ_RATE_LIMIT_PER_MINUTE", 120),
            read_rate_limit_burst=_int_from_env("MLB_READ_RATE_LIMIT_BURST", 30),
            admin_rate_limit_per_minute=_int_from_env("MLB_ADMIN_RATE_LIMIT_PER_MINUTE", 10),
            rate_limit_max_buckets=_int_from_env("MLB_RATE_LIMIT_MAX_BUCKETS", 8192),
            trusted_proxy_cidrs=_csv_tuple_from_env("MLB_TRUSTED_PROXY_CIDRS", ("127.0.0.1/32", "::1/128")),
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
