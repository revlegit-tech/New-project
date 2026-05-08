from __future__ import annotations

from tools.phase16_common import (
    eligible_live_features,
    implied_probability_from_american,
    match_key,
    normalized_market,
)
from tools.phase16_feature_contract import contract_for_market


def test_implied_probability_from_american_odds():
    assert round(implied_probability_from_american(-150), 4) == 0.6
    assert round(implied_probability_from_american(200), 4) == 0.3333


def test_match_key_normalizes_player_market_line_and_yes_side():
    row = {"player": "Manny Machado", "marketDisplay": "", "market": "Batter Hits", "line": "0.50", "rawLabel": "Yes"}
    assert match_key(row) == ("manny machado", "batter_hits", "0.5", "over")


def test_eligible_live_features_blocks_leakage_and_identifiers():
    features = ["line", "actual", "event_id", "american_odds", "team_moneyline"]
    assert eligible_live_features(features) == ["line", "american_odds", "team_moneyline"]


def test_normalized_market_accepts_string_or_row():
    assert normalized_market("Batter Total Bases") == "batter_total_bases"
    assert normalized_market({"baseMarket": "pitcher_strikeouts"}) == "pitcher_strikeouts"
