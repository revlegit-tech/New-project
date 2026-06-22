from __future__ import annotations

from pathlib import Path

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.feature_row_repository import WarehouseFeatureRowRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase

STATCAST_DATASETS: frozenset[str] = frozenset({"statcast_pitches"})


class StatcastRepository(WarehouseFeatureRowRepository):
    """DB-first/CSV-fallback repository for raw Statcast pitch rows."""

    def __init__(self, db: WarehouseDatabase, *, settings: Settings = default_settings) -> None:
        super().__init__(
            db,
            table_name="statcast_raw_rows",
            csv_root=settings.data_dir / "warehouse" / "statcast",
            allowed_datasets=set(STATCAST_DATASETS),
            id_prefix="statcast_row",
            settings=settings,
        )
