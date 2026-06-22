from __future__ import annotations

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.feature_row_repository import WarehouseFeatureRowRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase

GAME_ENVIRONMENT_DATASETS: frozenset[str] = frozenset(
    {
        "game_environment_daily",
        "bullpen_daily",
        "lineup_context_daily",
    }
)


class GameEnvironmentRepository(WarehouseFeatureRowRepository):
    """DB-first/CSV-fallback repository for game environment and context rows."""

    def __init__(self, db: WarehouseDatabase, *, settings: Settings = default_settings) -> None:
        super().__init__(
            db,
            table_name="game_environment_feature_rows",
            csv_root=settings.data_dir / "warehouse" / "game_environment",
            allowed_datasets=set(GAME_ENVIRONMENT_DATASETS),
            id_prefix="game_environment_row",
            settings=settings,
        )
