from __future__ import annotations

import json
from pathlib import Path

from mlb_app.ml.datasets.feature_matrix_builder import feature_names_for_market
from mlb_app.ml.datasets.leakage_guard import blocked_ml_feature_fields
from mlb_app.ml.market_config import (
    KNOWN_FEATURE_GROUPS,
    KNOWN_MODEL_NAMES,
    SUPPORTED_MARKETS,
    all_market_configs,
    feature_fields_for_market,
    validate_market_configs,
)


def test_every_supported_market_has_a_valid_config() -> None:
    configs = all_market_configs()

    assert set(configs) == set(SUPPORTED_MARKETS)
    assert validate_market_configs() == []


def test_every_config_has_training_thresholds() -> None:
    for config in all_market_configs().values():
        assert config.minimum_training_rows > 0
        assert config.minimum_positive_rows > 0
        assert config.minimum_training_rows >= config.minimum_positive_rows


def test_configs_reference_known_feature_groups_and_models() -> None:
    for config in all_market_configs().values():
        assert config.feature_groups
        assert config.candidate_models
        assert set(config.feature_groups) <= set(KNOWN_FEATURE_GROUPS)
        assert set(config.candidate_models) <= set(KNOWN_MODEL_NAMES)


def test_market_feature_groups_expand_to_leakage_safe_feature_names() -> None:
    for market in SUPPORTED_MARKETS:
        fields = feature_fields_for_market(market)

        assert fields
        assert feature_names_for_market(market) == list(fields)


def test_rare_event_markets_enable_class_imbalance_support() -> None:
    rare_configs = [config for config in all_market_configs().values() if config.rare_event]

    assert {config.market for config in rare_configs} >= {"batter_home_runs"}
    for config in rare_configs:
        assert config.class_imbalance_support is True
        assert "rare_event_ensemble" in config.candidate_models


def test_blocked_leakage_fields_are_included_for_every_market() -> None:
    blocked = blocked_ml_feature_fields()

    for config in all_market_configs().values():
        assert blocked <= set(config.blocked_feature_fields)


def test_example_market_model_config_matches_supported_market_list() -> None:
    path = Path("config/ml_market_models.example.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload["markets"]) == set(SUPPORTED_MARKETS)
    for market, config in payload["markets"].items():
        assert config["market"] == market
        assert config["minimum_training_rows"] > 0
        assert config["minimum_positive_rows"] > 0
        assert config["candidate_models"]
        assert config["feature_groups"]
        assert config["blocked_feature_fields"]
