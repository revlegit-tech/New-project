from __future__ import annotations

from mlb_app.services.playerboard_builder import normalize_prop_row


def test_participant_wins_over_dirty_name() -> None:
    row = normalize_prop_row(
        {
            "market": "pitcher_strikeouts",
            "name": "Kodai Senga Strikeouts Thrown",
            "participant": "Kodai Senga",
            "side": "Over",
            "line": "5.5",
            "americanOdds": "-110",
        },
        "2026-06-22",
    )

    assert row["player"] == "Kodai Senga"


def test_dirty_pitcher_name_fallback_is_suffix_stripped() -> None:
    row = normalize_prop_row(
        {
            "market": "pitcher_strikeouts",
            "name": "Kodai Senga Strikeouts Thrown",
            "side": "Over",
            "line": "5.5",
            "americanOdds": "-110",
        },
        "2026-06-22",
    )

    assert row["player"] == "Kodai Senga"


def test_dirty_batter_name_fallback_is_suffix_stripped() -> None:
    row = normalize_prop_row(
        {
            "market": "batter_home_runs",
            "name": "Juan Soto Home Runs",
            "side": "Over",
            "line": "0.5",
            "americanOdds": "+420",
        },
        "2026-06-22",
    )

    assert row["player"] == "Juan Soto"


def test_clean_player_name_remains_unchanged() -> None:
    row = normalize_prop_row(
        {
            "market": "batter_total_bases",
            "player": "Mookie Betts",
            "name": "Mookie Betts Total Bases",
            "side": "Over",
            "line": "1.5",
            "americanOdds": "-110",
        },
        "2026-06-22",
    )

    assert row["player"] == "Mookie Betts"
