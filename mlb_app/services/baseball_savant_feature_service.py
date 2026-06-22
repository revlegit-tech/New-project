from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mlb_app.repositories.feature_row_repository import FeatureRepositoryResult
from mlb_app.repositories.player_metric_repository import PLAYER_METRIC_DATASETS, PlayerMetricRepository
from mlb_app.repositories.warehouse_utils import clean, first
from mlb_app.services.game_environment_feature_service import (
    GAME_ENVIRONMENT_FEATURE_FIELDS,
    normalize_game_environment_row,
)
from mlb_app.services.ml_feature_schema import leakage_fields_in_payload

SAVANT_FEATURE_SCHEMA_VERSION = "baseball-savant-features.sprint15.v1"

SPLIT_SUFFIXES: tuple[str, ...] = (
    "_vs_lhp",
    "_vs_rhp",
    "_l7",
    "_l14",
    "_l30",
    "_season",
    "_home",
    "_away",
)

BATTER_STATCAST_FEATURE_FIELDS: tuple[str, ...] = (
    "barrel_rate",
    "hard_hit_rate",
    "avg_exit_velocity",
    "max_exit_velocity",
    "sweet_spot_rate",
    "launch_angle_avg",
    "xwoba",
    "xslg",
    "xba",
    "strikeout_rate",
    "walk_rate",
    "chase_rate",
    "contact_rate",
    "pull_rate",
    "fly_ball_rate",
    "ground_ball_rate",
    "line_drive_rate",
)

PITCHER_ANALYTICS_FEATURE_FIELDS: tuple[str, ...] = (
    "k_rate",
    "bb_rate",
    "csw_rate",
    "whiff_rate",
    "chase_rate",
    "zone_rate",
    "first_pitch_strike_rate",
    "called_strike_rate",
    "swinging_strike_rate",
    "avg_fastball_velocity",
    "velocity_delta_last_3",
    "spin_rate",
    "extension",
    "pitch_mix_fastball",
    "pitch_mix_slider",
    "pitch_mix_curveball",
    "pitch_mix_changeup",
    "pitch_mix_sweeper",
    "xwoba_allowed",
    "xba_allowed",
    "xslg_allowed",
    "barrel_rate_allowed",
    "hard_hit_rate_allowed",
    "avg_exit_velocity_allowed",
    "hr_per_9",
    "hits_allowed_per_pa",
    "earned_runs_per_ip",
    "projected_pitch_count",
    "last_start_pitch_count",
    "days_rest",
)

PITCH_TYPE_MATCHUP_FEATURE_FIELDS: tuple[str, ...] = (
    "pitcher_primary_pitch_type",
    "pitcher_secondary_pitch_type",
    "pitcher_pitch_mix_entropy",
    "batter_run_value_vs_fastball",
    "batter_run_value_vs_slider",
    "batter_run_value_vs_curveball",
    "batter_whiff_vs_pitcher_primary",
    "batter_xwoba_vs_pitcher_primary",
    "batter_slug_vs_pitcher_primary",
)


def _split_fields(fields: Sequence[str]) -> tuple[str, ...]:
    return tuple(f"{field}{suffix}" for field in fields for suffix in SPLIT_SUFFIXES)


SAVANT_JOIN_FIELDS: tuple[str, ...] = (
    "savant_schema_version",
    "dataset",
    "feature_date",
    "date",
    "season",
    "game_id",
    "player_id",
    "player_name",
    "team",
    "opponent",
    "pitch_type",
    "split",
    "handedness",
    "source",
    "source_path",
)

_DATASET_FIELDS: dict[str, tuple[str, ...]] = {
    "statcast_batter_daily": BATTER_STATCAST_FEATURE_FIELDS + _split_fields(BATTER_STATCAST_FEATURE_FIELDS),
    "statcast_pitcher_daily": PITCHER_ANALYTICS_FEATURE_FIELDS + _split_fields(PITCHER_ANALYTICS_FEATURE_FIELDS),
    "statcast_pitcher_arsenal_daily": PITCHER_ANALYTICS_FEATURE_FIELDS,
    "statcast_batter_pitch_type_daily": PITCH_TYPE_MATCHUP_FEATURE_FIELDS,
    "statcast_batter_handedness_daily": BATTER_STATCAST_FEATURE_FIELDS + _split_fields(BATTER_STATCAST_FEATURE_FIELDS),
    "statcast_pitcher_handedness_allowed_daily": PITCHER_ANALYTICS_FEATURE_FIELDS
    + _split_fields(PITCHER_ANALYTICS_FEATURE_FIELDS),
}


def safe_batter_statcast_feature_names() -> list[str]:
    return list(BATTER_STATCAST_FEATURE_FIELDS + _split_fields(BATTER_STATCAST_FEATURE_FIELDS))


def safe_pitcher_analytics_feature_names() -> list[str]:
    return list(PITCHER_ANALYTICS_FEATURE_FIELDS + _split_fields(PITCHER_ANALYTICS_FEATURE_FIELDS))


def safe_pitch_type_matchup_feature_names() -> list[str]:
    return list(PITCH_TYPE_MATCHUP_FEATURE_FIELDS)


def safe_savant_feature_names(dataset: str) -> list[str]:
    return list(_DATASET_FIELDS.get(clean(dataset), ()))


def assert_no_savant_leakage_fields(payload: Mapping[str, Any]) -> None:
    leaking = sorted(leakage_fields_in_payload(payload))
    if leaking:
        raise ValueError(f"Blocked leakage fields are not allowed in Savant features: {', '.join(leaking)}")


def normalize_savant_feature_row(
    row: Mapping[str, Any],
    *,
    dataset: str,
    date_label: str = "",
) -> dict[str, Any]:
    selected_dataset = _dataset(dataset)
    assert_no_savant_leakage_fields(row)
    feature_date = clean(first(row, "feature_date", "date", "game_date", "gameDate")) or clean(date_label)
    normalized: dict[str, Any] = {
        "savant_schema_version": SAVANT_FEATURE_SCHEMA_VERSION,
        "dataset": selected_dataset,
        "feature_date": feature_date,
        "date": feature_date,
        "season": row.get("season", ""),
        "game_id": clean(first(row, "game_id", "gamePk", "game_pk", "mlb_game_id")),
        "player_id": clean(first(row, "player_id", "mlbamId", "mlbam_id", "batter_id", "pitcher_id")),
        "player_name": clean(first(row, "player_name", "player", "name", "batter", "pitcher")),
        "team": clean(first(row, "team", "team_abbr", "teamAbbr", "batting_team", "pitching_team")).upper(),
        "opponent": clean(first(row, "opponent", "opponent_abbr", "opponentAbbr")).upper(),
        "pitch_type": clean(first(row, "pitch_type", "pitchType", "primary_pitch_type")),
        "split": clean(first(row, "split", "split_key", "window", "home_away")),
        "handedness": clean(first(row, "handedness", "stand", "p_throws", "throws")),
        "source": clean(first(row, "source", "provider")) or "local",
        "source_path": clean(first(row, "source_path", "sourcePath")),
    }
    for name in _DATASET_FIELDS[selected_dataset]:
        if name in row:
            normalized[name] = row.get(name)
    assert_no_savant_leakage_fields(normalized)
    return normalized


class BaseballSavantFeatureService:
    """Normalize, persist, and join safe Savant-style player metrics."""

    def __init__(self, repository: PlayerMetricRepository | None = None) -> None:
        self.repository = repository

    def normalize_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        dataset: str,
        date_label: str = "",
    ) -> list[dict[str, Any]]:
        return [normalize_savant_feature_row(row, dataset=dataset, date_label=date_label) for row in rows]

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
            raise RuntimeError("BaseballSavantFeatureService requires a repository to persist rows")
        normalized = self.normalize_rows(rows, dataset=dataset, date_label=date_label)
        return self.repository.upsert_rows(
            dataset,
            normalized,
            date_label=date_label,
            source_path=source_path,
            replace_csv=replace_csv,
        )

    def read_rows(self, dataset: str, *, date_label: str = "", player_id: str = "") -> list[dict[str, Any]]:
        if self.repository is None:
            return []
        return self.repository.read_rows(dataset, date_label=date_label, player_id=player_id)

    def build_matchup_feature_row(
        self,
        *,
        batter_row: Mapping[str, Any] | None = None,
        pitcher_row: Mapping[str, Any] | None = None,
        pitch_type_row: Mapping[str, Any] | None = None,
        environment_row: Mapping[str, Any] | None = None,
        date_label: str = "",
    ) -> dict[str, Any]:
        batter = normalize_savant_feature_row(
            batter_row or {},
            dataset=clean((batter_row or {}).get("dataset")) or "statcast_batter_daily",
            date_label=date_label,
        ) if batter_row else {}
        pitcher = normalize_savant_feature_row(
            pitcher_row or {},
            dataset=clean((pitcher_row or {}).get("dataset")) or "statcast_pitcher_daily",
            date_label=date_label,
        ) if pitcher_row else {}
        matchup = normalize_savant_feature_row(
            pitch_type_row or {},
            dataset=clean((pitch_type_row or {}).get("dataset")) or "statcast_batter_pitch_type_daily",
            date_label=date_label,
        ) if pitch_type_row else {}
        environment = (
            normalize_game_environment_row(environment_row, dataset=clean(environment_row.get("dataset")) or "game_environment_daily", date_label=date_label)
            if environment_row
            else {}
        )
        selected_date = clean(date_label) or clean(first(batter, "feature_date", "date")) or clean(first(pitcher, "feature_date", "date"))
        row: dict[str, Any] = {
            "savant_schema_version": SAVANT_FEATURE_SCHEMA_VERSION,
            "date": selected_date,
            "feature_date": selected_date,
            "season": first(batter, "season") or first(pitcher, "season") or first(environment, "season"),
            "game_id": first(environment, "game_id") or first(batter, "game_id") or first(pitcher, "game_id"),
            "player_id": first(batter, "player_id"),
            "player_name": first(batter, "player_name"),
            "team": first(batter, "team") or first(environment, "team"),
            "opponent": first(batter, "opponent") or first(environment, "opponent"),
            "pitcher_id": first(pitcher, "player_id"),
            "pitcher_name": first(pitcher, "player_name"),
        }
        row.update(_prefixed_features("batter", batter, BATTER_STATCAST_FEATURE_FIELDS + _split_fields(BATTER_STATCAST_FEATURE_FIELDS)))
        row.update(_prefixed_features("pitcher", pitcher, PITCHER_ANALYTICS_FEATURE_FIELDS + _split_fields(PITCHER_ANALYTICS_FEATURE_FIELDS)))
        for name in PITCH_TYPE_MATCHUP_FEATURE_FIELDS:
            if name in matchup:
                row[name] = matchup.get(name)
        for name in GAME_ENVIRONMENT_FEATURE_FIELDS:
            if name in environment:
                row[name] = environment.get(name)
        assert_no_savant_leakage_fields(row)
        return row


def _prefixed_features(prefix: str, row: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {f"{prefix}_{name}": row.get(name) for name in fields if name in row}


def _dataset(dataset: str) -> str:
    selected = clean(dataset)
    if selected not in PLAYER_METRIC_DATASETS:
        raise ValueError(f"Unsupported Savant feature dataset: {selected or '<empty>'}")
    return selected
