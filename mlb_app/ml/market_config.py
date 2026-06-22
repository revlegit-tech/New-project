from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlb_app.ml.datasets.leakage_guard import blocked_ml_feature_fields

SUPPORTED_MARKETS: tuple[str, ...] = (
    "pitcher_strikeouts",
    "pitcher_outs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "batter_rbis",
    "batter_runs",
    "batter_walks",
    "batter_stolen_bases",
)

KNOWN_MODEL_NAMES: frozenset[str] = frozenset(
    {
        "calibrated_logistic",
        "hist_gradient_boosting",
        "xgboost_classifier",
        "xgboost_regressor",
        "count_projection",
        "projection_model",
        "ensemble",
        "rare_event_ensemble",
    }
)

CLASS_IMBALANCE_MODEL_NAMES: frozenset[str] = frozenset(
    {
        "calibrated_logistic",
        "xgboost_classifier",
        "rare_event_ensemble",
    }
)

KNOWN_FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "pitcher_form": (
        "pitcher_recent_starts",
        "pitcher_recent_innings",
        "pitcher_recent_strikeouts",
        "pitcher_recent_k_rate",
        "pitcher_recent_walk_rate",
        "pitcher_season_k_rate",
    ),
    "opponent_k_profile": (
        "opponent_team_k_rate_vs_hand",
        "opponent_projected_lineup_k_rate",
        "opponent_chase_rate",
        "opponent_contact_rate",
    ),
    "pitch_mix": (
        "pitcher_fastball_pct",
        "pitcher_breaking_pct",
        "pitcher_offspeed_pct",
        "pitcher_primary_pitch_usage",
    ),
    "pitch_type_matchup": (
        "batter_run_value_vs_fastball",
        "batter_run_value_vs_breaking",
        "batter_whiff_rate_vs_primary_pitch",
        "pitcher_primary_pitch_whiff_rate",
        "opponent_xwoba_vs_primary_pitch",
    ),
    "game_environment": (
        "game_temperature",
        "game_wind_speed",
        "game_market_consensus_current_total",
        "game_market_team_no_vig_win_prob_current",
        "game_market_opponent_no_vig_win_prob_current",
    ),
    "market_odds": (
        "line",
        "american_odds",
        "implied_probability_percent",
        "model_probability_percent",
        "game_market_disagreement_score",
    ),
    "workload": (
        "pitcher_projected_pitch_count",
        "pitcher_recent_pitch_count_avg",
        "pitcher_days_rest",
        "pitcher_times_through_order_projection",
    ),
    "batter_power": (
        "batter_iso",
        "batter_barrel_rate",
        "batter_hard_hit_rate",
        "batter_xslg",
        "batter_recent_total_bases_rate",
    ),
    "pitcher_power_allowed": (
        "pitcher_hr_per_9_allowed",
        "pitcher_barrel_rate_allowed",
        "pitcher_hard_hit_rate_allowed",
        "pitcher_xslg_allowed",
    ),
    "park_weather": (
        "park_factor_runs",
        "park_factor_home_runs",
        "weather_temperature",
        "weather_wind_out_to_cf",
        "roof_status_code",
    ),
    "lineup_context": (
        "projected_batting_order",
        "lineup_spot",
        "projected_team_runs",
        "teammate_obp_ahead",
        "teammate_slg_behind",
    ),
    "batter_contact": (
        "batter_avg",
        "batter_xba",
        "batter_contact_rate",
        "batter_whiff_rate",
        "batter_recent_hits_rate",
    ),
    "pitcher_contact_allowed": (
        "pitcher_batting_avg_allowed",
        "pitcher_xba_allowed",
        "pitcher_contact_rate_allowed",
        "pitcher_whiff_rate",
    ),
    "handedness_split": (
        "batter_split_woba",
        "batter_split_iso",
        "pitcher_split_woba_allowed",
        "pitcher_split_k_rate",
    ),
    "projected_plate_appearances": (
        "projected_plate_appearances",
        "lineup_spot_plate_appearance_avg",
        "team_projected_at_bats",
    ),
    "pitcher_xslg_allowed": (
        "pitcher_xslg_allowed",
        "pitcher_xwoba_allowed",
        "pitcher_barrel_rate_allowed",
        "pitcher_hard_hit_rate_allowed",
    ),
    "pitcher_quality_allowed": (
        "pitcher_era",
        "pitcher_xera",
        "pitcher_whip",
        "pitcher_fip",
        "pitcher_recent_run_allowed_rate",
    ),
    "opponent_team_offense": (
        "opponent_team_woba_vs_hand",
        "opponent_team_iso_vs_hand",
        "opponent_team_runs_per_game",
        "opponent_projected_lineup_woba",
    ),
    "bullpen_context": (
        "bullpen_recent_workload",
        "bullpen_fatigue_score",
        "bullpen_era",
        "bullpen_availability_score",
    ),
    "batter_plate_discipline": (
        "batter_walk_rate",
        "batter_chase_rate",
        "batter_zone_contact_rate",
        "batter_recent_walk_rate",
    ),
    "pitcher_control": (
        "pitcher_walk_rate_allowed",
        "pitcher_zone_rate",
        "pitcher_first_pitch_strike_rate",
        "pitcher_recent_walks_allowed_rate",
    ),
    "baserunning_speed": (
        "batter_sprint_speed",
        "batter_stolen_base_attempt_rate",
        "batter_recent_stolen_base_rate",
        "batter_on_base_frequency",
    ),
    "catcher_run_game": (
        "opposing_catcher_pop_time",
        "opposing_catcher_caught_stealing_rate",
        "opposing_team_stolen_bases_allowed",
    ),
    "pitcher_hold_context": (
        "pitcher_stolen_bases_allowed",
        "pitcher_pickoff_rate",
        "pitcher_time_to_plate",
    ),
}

_BLOCKED_FEATURE_FIELDS = tuple(sorted(blocked_ml_feature_fields()))


@dataclass(frozen=True)
class MarketModelConfig:
    market: str
    target_type: str
    actual_value_field: str
    default_side_logic: str
    minimum_training_rows: int
    minimum_positive_rows: int
    candidate_models: tuple[str, ...]
    feature_groups: tuple[str, ...]
    blocked_feature_fields: tuple[str, ...]
    recommended_calibration: str
    rare_event: bool = False
    class_imbalance_support: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "target_type": self.target_type,
            "actual_value_field": self.actual_value_field,
            "default_side_logic": self.default_side_logic,
            "minimum_training_rows": self.minimum_training_rows,
            "minimum_positive_rows": self.minimum_positive_rows,
            "candidate_models": list(self.candidate_models),
            "feature_groups": list(self.feature_groups),
            "blocked_feature_fields": list(self.blocked_feature_fields),
            "recommended_calibration": self.recommended_calibration,
            "rare_event": self.rare_event,
            "class_imbalance_support": self.class_imbalance_support,
        }


def get_market_config(market: str) -> MarketModelConfig:
    key = normalize_market(market)
    try:
        return MARKET_CONFIGS[key]
    except KeyError as error:
        raise KeyError(f"Unsupported MLB prop market: {market}") from error


def is_supported_market(market: str) -> bool:
    return normalize_market(market) in MARKET_CONFIGS


def supported_markets() -> tuple[str, ...]:
    return SUPPORTED_MARKETS


def all_market_configs() -> dict[str, MarketModelConfig]:
    return dict(MARKET_CONFIGS)


def feature_group_fields(group: str) -> tuple[str, ...]:
    try:
        return KNOWN_FEATURE_GROUPS[str(group)]
    except KeyError as error:
        raise KeyError(f"Unknown MLB feature group: {group}") from error


def feature_fields_for_market(market: str) -> tuple[str, ...]:
    config = get_market_config(market)
    fields: list[str] = []
    for group in config.feature_groups:
        fields.extend(feature_group_fields(group))
    return tuple(dict.fromkeys(fields))


def validate_market_configs() -> list[str]:
    errors: list[str] = []
    for market in SUPPORTED_MARKETS:
        config = MARKET_CONFIGS.get(market)
        if config is None:
            errors.append(f"{market}: missing market config")
            continue
        if config.minimum_training_rows <= 0:
            errors.append(f"{market}: minimum_training_rows must be positive")
        if config.minimum_positive_rows <= 0:
            errors.append(f"{market}: minimum_positive_rows must be positive")
        for group in config.feature_groups:
            if group not in KNOWN_FEATURE_GROUPS:
                errors.append(f"{market}: unknown feature group {group}")
        for model in config.candidate_models:
            if model not in KNOWN_MODEL_NAMES:
                errors.append(f"{market}: unknown candidate model {model}")
        if config.rare_event and not config.class_imbalance_support:
            errors.append(f"{market}: rare-event markets must enable class_imbalance_support")
        blocked = set(config.blocked_feature_fields)
        missing_blocked = set(_BLOCKED_FEATURE_FIELDS) - blocked
        if missing_blocked:
            sample = ", ".join(sorted(missing_blocked)[:5])
            errors.append(f"{market}: missing blocked leakage fields: {sample}")
    extra = sorted(set(MARKET_CONFIGS) - set(SUPPORTED_MARKETS))
    for market in extra:
        errors.append(f"{market}: config is not in SUPPORTED_MARKETS")
    return errors


def normalize_market(market: str) -> str:
    text = str(market or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _market_config(
    *,
    market: str,
    target_type: str,
    actual_value_field: str,
    default_side_logic: str = "over_under_push",
    minimum_training_rows: int = 250,
    minimum_positive_rows: int = 40,
    candidate_models: tuple[str, ...],
    feature_groups: tuple[str, ...],
    recommended_calibration: str = "sigmoid_or_isotonic_after_walk_forward_validation",
    rare_event: bool = False,
) -> MarketModelConfig:
    return MarketModelConfig(
        market=market,
        target_type=target_type,
        actual_value_field=actual_value_field,
        default_side_logic=default_side_logic,
        minimum_training_rows=minimum_training_rows,
        minimum_positive_rows=minimum_positive_rows,
        candidate_models=candidate_models,
        feature_groups=feature_groups,
        blocked_feature_fields=_BLOCKED_FEATURE_FIELDS,
        recommended_calibration=recommended_calibration,
        rare_event=rare_event,
        class_imbalance_support=rare_event,
    )


MARKET_CONFIGS: dict[str, MarketModelConfig] = {
    "pitcher_strikeouts": _market_config(
        market="pitcher_strikeouts",
        target_type="over_under",
        actual_value_field="actual_strikeouts",
        minimum_training_rows=400,
        minimum_positive_rows=80,
        candidate_models=(
            "calibrated_logistic",
            "hist_gradient_boosting",
            "xgboost_classifier",
            "count_projection",
            "ensemble",
        ),
        feature_groups=(
            "pitcher_form",
            "opponent_k_profile",
            "pitch_mix",
            "pitch_type_matchup",
            "game_environment",
            "market_odds",
            "workload",
        ),
    ),
    "pitcher_outs": _market_config(
        market="pitcher_outs",
        target_type="over_under",
        actual_value_field="actual_outs",
        minimum_training_rows=300,
        minimum_positive_rows=60,
        candidate_models=(
            "calibrated_logistic",
            "hist_gradient_boosting",
            "xgboost_classifier",
            "count_projection",
            "ensemble",
        ),
        feature_groups=(
            "pitcher_form",
            "opponent_team_offense",
            "pitch_mix",
            "game_environment",
            "market_odds",
            "workload",
        ),
    ),
    "pitcher_hits_allowed": _market_config(
        market="pitcher_hits_allowed",
        target_type="over_under",
        actual_value_field="actual_hits_allowed",
        minimum_training_rows=300,
        minimum_positive_rows=60,
        candidate_models=(
            "calibrated_logistic",
            "xgboost_classifier",
            "count_projection",
            "ensemble",
        ),
        feature_groups=(
            "pitcher_quality_allowed",
            "opponent_team_offense",
            "park_weather",
            "bullpen_context",
            "workload",
            "market_odds",
        ),
    ),
    "pitcher_earned_runs": _market_config(
        market="pitcher_earned_runs",
        target_type="over_under",
        actual_value_field="actual_earned_runs",
        minimum_training_rows=300,
        minimum_positive_rows=60,
        candidate_models=(
            "calibrated_logistic",
            "xgboost_classifier",
            "count_projection",
            "ensemble",
        ),
        feature_groups=(
            "pitcher_quality_allowed",
            "opponent_team_offense",
            "park_weather",
            "bullpen_context",
            "workload",
            "market_odds",
        ),
    ),
    "batter_hits": _market_config(
        market="batter_hits",
        target_type="over_under",
        actual_value_field="actual_hits",
        minimum_training_rows=500,
        minimum_positive_rows=100,
        candidate_models=(
            "calibrated_logistic",
            "hist_gradient_boosting",
            "xgboost_classifier",
            "projection_model",
        ),
        feature_groups=(
            "batter_contact",
            "pitcher_contact_allowed",
            "handedness_split",
            "projected_plate_appearances",
            "game_environment",
            "market_odds",
        ),
    ),
    "batter_total_bases": _market_config(
        market="batter_total_bases",
        target_type="over_under",
        actual_value_field="actual_total_bases",
        minimum_training_rows=500,
        minimum_positive_rows=100,
        candidate_models=(
            "calibrated_logistic",
            "xgboost_classifier",
            "xgboost_regressor",
            "ensemble",
        ),
        feature_groups=(
            "batter_power",
            "batter_contact",
            "pitcher_xslg_allowed",
            "pitch_type_matchup",
            "park_weather",
            "market_odds",
        ),
    ),
    "batter_home_runs": _market_config(
        market="batter_home_runs",
        target_type="event_or_line",
        actual_value_field="actual_home_runs",
        default_side_logic="home_run_yes_or_line",
        minimum_training_rows=1000,
        minimum_positive_rows=40,
        candidate_models=(
            "calibrated_logistic",
            "xgboost_classifier",
            "rare_event_ensemble",
        ),
        feature_groups=(
            "batter_power",
            "pitcher_power_allowed",
            "pitch_type_matchup",
            "park_weather",
            "lineup_context",
            "market_odds",
        ),
        recommended_calibration="sigmoid_with_class_weight_and_precision_recall_monitoring",
        rare_event=True,
    ),
    "batter_rbis": _market_config(
        market="batter_rbis",
        target_type="over_under",
        actual_value_field="actual_rbis",
        minimum_training_rows=400,
        minimum_positive_rows=70,
        candidate_models=(
            "calibrated_logistic",
            "hist_gradient_boosting",
            "xgboost_classifier",
            "projection_model",
            "ensemble",
        ),
        feature_groups=(
            "batter_power",
            "batter_contact",
            "pitcher_contact_allowed",
            "lineup_context",
            "park_weather",
            "market_odds",
        ),
    ),
    "batter_runs": _market_config(
        market="batter_runs",
        target_type="over_under",
        actual_value_field="actual_runs",
        minimum_training_rows=400,
        minimum_positive_rows=70,
        candidate_models=(
            "calibrated_logistic",
            "hist_gradient_boosting",
            "xgboost_classifier",
            "projection_model",
            "ensemble",
        ),
        feature_groups=(
            "batter_contact",
            "lineup_context",
            "projected_plate_appearances",
            "game_environment",
            "market_odds",
        ),
    ),
    "batter_walks": _market_config(
        market="batter_walks",
        target_type="over_under",
        actual_value_field="actual_walks",
        minimum_training_rows=350,
        minimum_positive_rows=60,
        candidate_models=(
            "calibrated_logistic",
            "hist_gradient_boosting",
            "xgboost_classifier",
            "projection_model",
            "ensemble",
        ),
        feature_groups=(
            "batter_plate_discipline",
            "pitcher_control",
            "handedness_split",
            "projected_plate_appearances",
            "game_environment",
            "market_odds",
        ),
    ),
    "batter_stolen_bases": _market_config(
        market="batter_stolen_bases",
        target_type="over_under",
        actual_value_field="actual_stolen_bases",
        minimum_training_rows=800,
        minimum_positive_rows=35,
        candidate_models=(
            "calibrated_logistic",
            "xgboost_classifier",
            "rare_event_ensemble",
        ),
        feature_groups=(
            "baserunning_speed",
            "catcher_run_game",
            "pitcher_hold_context",
            "lineup_context",
            "market_odds",
        ),
        recommended_calibration="sigmoid_with_class_weight_and_precision_recall_monitoring",
        rare_event=True,
    ),
}
