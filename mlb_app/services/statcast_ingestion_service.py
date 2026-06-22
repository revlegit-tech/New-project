from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mlb_app.repositories.feature_row_repository import FeatureRepositoryResult
from mlb_app.repositories.player_metric_repository import PLAYER_METRIC_DATASETS, PlayerMetricRepository
from mlb_app.repositories.statcast_repository import STATCAST_DATASETS, StatcastRepository
from mlb_app.repositories.warehouse_utils import clean
from mlb_app.services.baseball_savant_feature_service import BaseballSavantFeatureService


class StatcastIngestionService:
    """Import local deterministic Statcast/Savant rows without network access."""

    def __init__(
        self,
        *,
        statcast_repository: StatcastRepository,
        player_metric_repository: PlayerMetricRepository,
        savant_feature_service: BaseballSavantFeatureService | None = None,
    ) -> None:
        self.statcast_repository = statcast_repository
        self.player_metric_repository = player_metric_repository
        self.savant_feature_service = savant_feature_service or BaseballSavantFeatureService(player_metric_repository)

    def ingest_rows(
        self,
        dataset: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        date_label: str = "",
        source_path: str | Path = "",
        replace_csv: bool = False,
    ) -> FeatureRepositoryResult:
        selected = clean(dataset)
        if selected in STATCAST_DATASETS:
            return self.statcast_repository.upsert_rows(
                selected,
                rows,
                date_label=date_label,
                source_path=source_path,
                replace_csv=replace_csv,
            )
        if selected in PLAYER_METRIC_DATASETS:
            return self.savant_feature_service.upsert_rows(
                selected,
                rows,
                date_label=date_label,
                source_path=str(source_path),
                replace_csv=replace_csv,
            )
        raise ValueError(f"Unsupported Statcast ingestion dataset: {selected or '<empty>'}")

    def ingest_csv(
        self,
        dataset: str,
        source_file: str | Path,
        *,
        date_label: str = "",
        replace_csv: bool = False,
    ) -> FeatureRepositoryResult:
        path = Path(source_file)
        rows = _read_csv(path)
        return self.ingest_rows(dataset, rows, date_label=date_label, source_path=path, replace_csv=replace_csv)

    def read_rows(self, dataset: str, *, date_label: str = "") -> list[dict[str, Any]]:
        selected = clean(dataset)
        if selected in STATCAST_DATASETS:
            return self.statcast_repository.read_rows(selected, date_label=date_label)
        if selected in PLAYER_METRIC_DATASETS:
            return self.player_metric_repository.read_rows(selected, date_label=date_label)
        raise ValueError(f"Unsupported Statcast ingestion dataset: {selected or '<empty>'}")


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]
