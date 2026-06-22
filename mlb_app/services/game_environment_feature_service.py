from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mlb_app.repositories.feature_row_repository import FeatureRepositoryResult
from mlb_app.repositories.game_environment_repository import GAME_ENVIRONMENT_DATASETS, GameEnvironmentRepository
from mlb_app.repositories.warehouse_utils import clean, first
from mlb_app.services.ml_feature_schema import leakage_fields_in_payload

GAME_ENVIRONMENT_SCHEMA_VERSION = "game-environment-features.sprint15.v1"

GAME_ENVIRONMENT_FEATURE_FIELDS: tuple[str, ...] = (
    "park",
    "park_factor_runs",
    "park_factor_hr_lhh",
    "park_factor_hr_rhh",
    "temperature",
    "wind_speed",
    "wind_direction",
    "wind_out_to_cf",
    "humidity",
    "roof_status",
    "altitude",
    "game_time_local",
    "day_night",
    "umpire_if_available",
)

BULLPEN_FEATURE_FIELDS: tuple[str, ...] = (
    "bullpen_usage_l1",
    "bullpen_usage_l3",
    "bullpen_rest_rank",
    "bullpen_availability_score",
    "closer_available",
    "setup_available",
)

LINEUP_CONTEXT_FEATURE_FIELDS: tuple[str, ...] = (
    "confirmed_lineup",
    "projected_lineup_slot",
    "projected_lineup_strength",
    "team_implied_runs",
    "batter_order_context",
)

ENVIRONMENT_JOIN_FIELDS: tuple[str, ...] = (
    "environment_schema_version",
    "dataset",
    "feature_date",
    "date",
    "season",
    "game_id",
    "home_team",
    "away_team",
    "team",
    "opponent",
    "source",
    "source_path",
)

_DATASET_FIELDS: dict[str, tuple[str, ...]] = {
    "game_environment_daily": GAME_ENVIRONMENT_FEATURE_FIELDS,
    "bullpen_daily": BULLPEN_FEATURE_FIELDS,
    "lineup_context_daily": LINEUP_CONTEXT_FEATURE_FIELDS,
}


def safe_game_environment_feature_names(dataset: str = "game_environment_daily") -> list[str]:
    return list(_DATASET_FIELDS.get(clean(dataset), GAME_ENVIRONMENT_FEATURE_FIELDS))


def safe_game_environment_column_names(dataset: str = "game_environment_daily") -> list[str]:
    fields = _DATASET_FIELDS.get(clean(dataset), GAME_ENVIRONMENT_FEATURE_FIELDS)
    return list(ENVIRONMENT_JOIN_FIELDS + fields)


def assert_no_environment_leakage_fields(payload: Mapping[str, Any]) -> None:
    leaking = sorted(leakage_fields_in_payload(payload))
    if leaking:
        raise ValueError(f"Blocked leakage fields are not allowed in game environment features: {', '.join(leaking)}")


def normalize_game_environment_row(
    row: Mapping[str, Any],
    *,
    dataset: str = "game_environment_daily",
    date_label: str = "",
) -> dict[str, Any]:
    selected_dataset = _dataset(dataset)
    assert_no_environment_leakage_fields(row)
    feature_date = clean(first(row, "feature_date", "date", "game_date", "gameDate")) or clean(date_label)
    normalized: dict[str, Any] = {
        "environment_schema_version": GAME_ENVIRONMENT_SCHEMA_VERSION,
        "dataset": selected_dataset,
        "feature_date": feature_date,
        "date": feature_date,
        "season": row.get("season", ""),
        "game_id": clean(first(row, "game_id", "gamePk", "game_pk", "mlb_game_id")),
        "home_team": clean(first(row, "home_team", "homeTeam")).upper(),
        "away_team": clean(first(row, "away_team", "awayTeam")).upper(),
        "team": clean(first(row, "team", "team_abbr", "teamAbbr")).upper(),
        "opponent": clean(first(row, "opponent", "opponent_abbr", "opponentAbbr")).upper(),
        "source": clean(first(row, "source", "provider")) or "local",
        "source_path": clean(first(row, "source_path", "sourcePath")),
    }
    for name in _DATASET_FIELDS[selected_dataset]:
        if name in row:
            normalized[name] = row.get(name)
    assert_no_environment_leakage_fields(normalized)
    return normalized


class GameEnvironmentFeatureService:
    """Normalize and persist game-level environment/context features."""

    def __init__(self, repository: GameEnvironmentRepository | None = None) -> None:
        self.repository = repository

    def normalize_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        dataset: str = "game_environment_daily",
        date_label: str = "",
    ) -> list[dict[str, Any]]:
        return [normalize_game_environment_row(row, dataset=dataset, date_label=date_label) for row in rows]

    def upsert_rows(
        self,
        dataset: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        date_label: str = "",
        source_path: str = "",
        replace_csv: bool = False,
    ) -> FeatureRepositoryResult:
        if self.repository is None:
            raise RuntimeError("GameEnvironmentFeatureService requires a repository to persist rows")
        normalized = self.normalize_rows(rows, dataset=dataset, date_label=date_label)
        return self.repository.upsert_rows(
            dataset,
            normalized,
            date_label=date_label,
            source_path=source_path,
            replace_csv=replace_csv,
        )

    def read_rows(self, dataset: str, *, date_label: str = "", game_id: str = "") -> list[dict[str, Any]]:
        if self.repository is None:
            return []
        return self.repository.read_rows(dataset, date_label=date_label, game_id=game_id)


def _dataset(dataset: str) -> str:
    selected = clean(dataset)
    if selected not in GAME_ENVIRONMENT_DATASETS:
        raise ValueError(f"Unsupported game environment dataset: {selected or '<empty>'}")
    return selected
