from __future__ import annotations

from typing import Any

from mlb_app.services.game_market_feature_lookup_service import GameMarketFeatureLookupService
from mlb_app.services.player_attribution import apply_attribution, clean_player_label


def test_pitcher_label_cleanup_strips_market_suffix() -> None:
    assert clean_player_label("Freddy Peralta Strikeouts Thrown")["cleanedPlayerName"] == "Freddy Peralta"
    assert clean_player_label("Paul Skenes Strikeouts Thrown")["cleanedPlayerName"] == "Paul Skenes"
    assert clean_player_label("Troy Melton Strikeouts Thrown")["cleanedPlayerName"] == "Troy Melton"


def test_invalid_ladder_labels_are_not_treated_as_players() -> None:
    for label in ("3+ Strikeouts", "4+ Strikeouts"):
        resolved = apply_attribution({"player": label, "team": "MIL", "opponent": "CHC", "market": "pitcher_strikeouts_alt"})

        assert resolved["playerVerified"] is False
        assert resolved["attributionStatus"] == "invalid_player_label"
        assert resolved["contextBlockedByAttribution"] is True


def test_suspicious_team_conflicts_downgrade_and_block_context() -> None:
    examples = [
        ("Jazz Chisholm", "DET"),
        ("Jasson Dominguez", "DET"),
        ("Vladimir Guerrero Jr.", "NYM"),
    ]

    for player, wrong_team in examples:
        resolved = apply_attribution({"player": player, "team": wrong_team, "opponent": "NYY", "market": "batter_hits"})

        assert resolved["attributionStatus"] == "conflict"
        assert resolved["attributionConfidence"] == "low"
        assert resolved["teamVerified"] is False
        assert resolved["contextBlockedByAttribution"] is True
        assert "possible_team_mismatch" in resolved["attributionWarnings"]


def test_missing_source_team_keeps_row_visible_but_unverified() -> None:
    resolved = apply_attribution({"player": "Aaron Judge", "team": "", "opponent": "BAL", "market": "batter_hits"})

    assert resolved["player"] == "Aaron Judge"
    assert resolved["attributionStatus"] == "source_missing"
    assert resolved["attributionConfidence"] == "medium"
    assert resolved["teamVerified"] is False
    assert resolved["contextAllowedWithWarning"] is True


def test_game_market_context_blocks_conflicting_attribution() -> None:
    service = GameMarketFeatureLookupService(repository=None)
    rows = service.enrich_rows(
        [
            {
                "date": "2026-07-01",
                "player": "Jazz Chisholm",
                "team": "DET",
                "opponent": "NYY",
                "market": "batter_hits",
            }
        ]
    )

    assert rows[0]["game_market_available"] is False
    assert rows[0]["game_market_enrichment_status"] == "context_limited_by_attribution"

