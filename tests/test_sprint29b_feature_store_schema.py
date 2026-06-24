from __future__ import annotations

from mlb_app.contracts.feature_store_schema import (
    fields_for_group,
    feature_store_contract,
    postgame_label_names,
    pregame_feature_names,
)


def test_labels_and_outcomes_are_not_pregame_safe() -> None:
    label_fields = fields_for_group("labels")

    assert label_fields
    assert all(field.pregame_safe is False for field in label_fields)
    assert {"actual_value", "result", "hit", "graded_at"} <= set(postgame_label_names())
    assert "actual_value" not in pregame_feature_names()


def test_market_weather_savant_and_umpire_fields_are_grouped() -> None:
    contract = feature_store_contract()
    groups = contract["groups"]

    assert {"line", "american_odds", "implied_probability_percent"} <= {field["name"] for field in groups["market"]}
    assert {"weather_temperature_f", "weather_wind_mph"} <= {field["name"] for field in groups["weather"]}
    assert {"batter_xba", "batter_hard_hit_rate"} <= {field["name"] for field in groups["batterSavant"]}
    assert {"pitcher_whiff_rate", "pitcher_xwoba_allowed"} <= {field["name"] for field in groups["pitcherSavant"]}
    assert {"umpire_name", "umpire_k_boost"} <= {field["name"] for field in groups["umpire"]}


def test_contract_declares_no_leakage_policy() -> None:
    contract = feature_store_contract()

    assert contract["schemaVersion"] == "mlb-feature-store-contract.v1"
    assert contract["leakagePolicy"]["predictionFieldsRequirePregameSafe"] is True
    assert contract["leakagePolicy"]["labelsPregameSafe"] is False
