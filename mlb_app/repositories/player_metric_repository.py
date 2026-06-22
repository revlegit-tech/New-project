from __future__ import annotations

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.feature_row_repository import WarehouseFeatureRowRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase

PLAYER_METRIC_DATASETS: frozenset[str] = frozenset(
    {
        "statcast_batter_daily",
        "statcast_pitcher_daily",
        "statcast_pitcher_arsenal_daily",
        "statcast_batter_pitch_type_daily",
        "statcast_batter_handedness_daily",
        "statcast_pitcher_handedness_allowed_daily",
    }
)


class PlayerMetricRepository(WarehouseFeatureRowRepository):
    """DB-first/CSV-fallback repository for Savant-style player feature rows."""

    def __init__(self, db: WarehouseDatabase, *, settings: Settings = default_settings) -> None:
        super().__init__(
            db,
            table_name="player_metric_feature_rows",
            csv_root=settings.data_dir / "warehouse" / "savant_features",
            allowed_datasets=set(PLAYER_METRIC_DATASETS),
            id_prefix="player_metric_row",
            settings=settings,
        )
