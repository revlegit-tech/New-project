from __future__ import annotations

from typing import Any

from mlb_app.services.game_market_feature_lookup_service import GameMarketFeatureLookupService
from mlb_app.services.player_attribution import apply_attribution, clean_player_label
from mlb_app.services.player_team_resolver import SlateRosterIndex, normalize_player_name


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


def test_roster_backed_game_side_correction_unblocks_context() -> None:
    examples = [
        ("Bobby Witt", "TBR", "KCR", "KANSAS CITY ROYALS", "TAMPA BAY RAYS"),
        ("Bobby Witt Jr.", "TBR", "KCR", "KANSAS CITY ROYALS", "TAMPA BAY RAYS"),
        ("Trea Turner", "PIT", "PHI", "PHILADELPHIA PHILLIES", "PITTSBURGH PIRATES"),
        ("Jose Altuve", "MIN", "HOU", "HOUSTON ASTROS", "MINNESOTA TWINS"),
        ("Christian Yelich", "CIN", "MIL", "MILWAUKEE BREWERS", "CINCINNATI REDS"),
        ("Jazz Chisholm", "DET", "NYY", "NEW YORK YANKEES", "DETROIT TIGERS"),
        ("Jasson Dominguez", "DET", "NYY", "NEW YORK YANKEES", "DETROIT TIGERS"),
        ("Vladimir Guerrero Jr.", "NYM", "TOR", "TORONTO BLUE JAYS", "NEW YORK METS"),
        ("Will Warren", "DET", "NYY", "NEW YORK YANKEES", "DETROIT TIGERS"),
    ]

    for player, wrong_team, opponent, expected_team, expected_opponent in examples:
        resolved = apply_attribution({"player": player, "team": wrong_team, "opponent": opponent, "market": "batter_hits"})

        assert resolved["attributionStatus"] == "corrected"
        assert resolved["attributionConfidence"] == "high"
        assert resolved["team"] == expected_team
        assert resolved["opponent"] == expected_opponent
        assert resolved["resolvedTeam"] == expected_team
        assert resolved["resolvedOpponent"] == expected_opponent
        assert resolved["attributionCorrectionApplied"] is True
        assert resolved["playerTeamEvidenceStatus"] == "roster_match"
        assert resolved["teamVerified"] is True
        assert resolved["opponentVerified"] is True
        assert resolved["contextBlockedByAttribution"] is False
        assert "source_team_mismatch_corrected" in resolved["attributionWarnings"]


def test_slate_roster_index_resolves_regression_examples_without_player_seeds() -> None:
    roster = SlateRosterIndex()
    for team, players in {
        "LAD": ["Shohei Ohtani"],
        "PHI": ["Kyle Schwarber", "Bryce Harper", "Trea Turner"],
        "KCR": ["Bobby Witt Jr.", "Salvador Perez"],
        "MIL": ["Christian Yelich", "Jackson Chourio", "William Contreras"],
        "CLE": ["Steven Kwan"],
        "SEA": ["Julio Rodriguez"],
        "ATL": ["Michael Harris II", "Ozzie Albies", "Matt Olson"],
    }.items():
        for player in players:
            roster.add_player(team, player)

    examples = [
        ("Shohei Ohtani", "SDP", "LAD", "LOS ANGELES DODGERS", "SAN DIEGO PADRES"),
        ("Kyle Schwarber", "PIT", "PHI", "PHILADELPHIA PHILLIES", "PITTSBURGH PIRATES"),
        ("Bryce Harper", "PIT", "PHI", "PHILADELPHIA PHILLIES", "PITTSBURGH PIRATES"),
        ("Trea Turner", "PIT", "PHI", "PHILADELPHIA PHILLIES", "PITTSBURGH PIRATES"),
        ("Bobby Witt", "TBR", "KCR", "KANSAS CITY ROYALS", "TAMPA BAY RAYS"),
        ("Bobby Witt Jr.", "TBR", "KCR", "KANSAS CITY ROYALS", "TAMPA BAY RAYS"),
        ("Salvador Perez", "TBR", "KCR", "KANSAS CITY ROYALS", "TAMPA BAY RAYS"),
        ("Christian Yelich", "CIN", "MIL", "MILWAUKEE BREWERS", "CINCINNATI REDS"),
        ("Jackson Chourio", "CIN", "MIL", "MILWAUKEE BREWERS", "CINCINNATI REDS"),
        ("William Contreras", "CIN", "MIL", "MILWAUKEE BREWERS", "CINCINNATI REDS"),
        ("Steven Kwan", "CHW", "CLE", "CLEVELAND GUARDIANS", "CHICAGO WHITE SOX"),
        ("Julio Rodriguez", "LAA", "SEA", "SEATTLE MARINERS", "LOS ANGELES ANGELS"),
        ("Michael Harris", "STL", "ATL", "ATLANTA BRAVES", "ST. LOUIS CARDINALS"),
        ("Michael Harris II", "STL", "ATL", "ATLANTA BRAVES", "ST. LOUIS CARDINALS"),
        ("Ozzie Albies", "STL", "ATL", "ATLANTA BRAVES", "ST. LOUIS CARDINALS"),
        ("Matt Olson", "STL", "ATL", "ATLANTA BRAVES", "ST. LOUIS CARDINALS"),
    ]

    for player, wrong_team, opponent, expected_team, expected_opponent in examples:
        resolved = apply_attribution(
            {"player": player, "team": wrong_team, "opponent": opponent, "market": "batter_hits"},
            roster_index=roster,
        )

        assert resolved["team"] == expected_team
        assert resolved["opponent"] == expected_opponent
        assert resolved["attributionStatus"] == "corrected"
        assert resolved["attributionConfidence"] == "high"
        assert resolved["playerTeamEvidenceStatus"] == "roster_match"
        assert resolved["contextBlockedByAttribution"] is False


def test_roster_evidence_outside_event_remains_conflict_gated() -> None:
    resolved = apply_attribution({"player": "Jazz Chisholm", "team": "DET", "opponent": "BAL", "market": "batter_hits"})

    assert resolved["attributionStatus"] == "conflict"
    assert resolved["attributionConfidence"] == "low"
    assert resolved["teamVerified"] is False
    assert resolved["contextBlockedByAttribution"] is True
    assert "possible_team_mismatch" in resolved["attributionWarnings"]


def test_missing_source_team_keeps_row_visible_but_unverified() -> None:
    resolved = apply_attribution({"player": "Aaron Judge", "team": "", "opponent": "BAL", "market": "batter_hits"})

    assert resolved["player"] == "Aaron Judge"
    assert resolved["attributionStatus"] == "source_missing"
    assert resolved["attributionConfidence"] == "low"
    assert resolved["teamVerified"] is False
    assert resolved["contextBlockedByAttribution"] is True


def test_game_market_context_blocks_conflicting_attribution() -> None:
    service = GameMarketFeatureLookupService(repository=None)
    rows = service.enrich_rows(
        [
            {
                "date": "2026-07-01",
                "player": "Jazz Chisholm",
                "team": "DET",
                "opponent": "BAL",
                "market": "batter_hits",
            }
        ]
    )

    assert rows[0]["game_market_available"] is False
    assert rows[0]["game_market_enrichment_status"] == "context_limited_by_attribution"


def test_pitcher_suffix_cleanup_does_not_falsely_verify_without_event_evidence() -> None:
    resolved = apply_attribution({"player": "Freddy Peralta Strikeouts Thrown", "team": "", "opponent": "", "market": "pitcher_strikeouts"})

    assert resolved["player"] == "Freddy Peralta"
    assert resolved["attributionStatus"] == "source_missing"
    assert resolved["teamVerified"] is False
    assert resolved["attributionCorrectionApplied"] is False


def test_ambiguous_player_match_does_not_correct() -> None:
    resolved = apply_attribution({"player": "Luis Garcia", "team": "HOU", "opponent": "WSN", "market": "pitcher_strikeouts"})

    assert resolved["attributionStatus"] == "ambiguous"
    assert resolved["attributionConfidence"] == "low"
    assert resolved["attributionCorrectionApplied"] is False
    assert resolved["contextBlockedByAttribution"] is True


def test_player_name_normalization_is_accent_insensitive_and_suffix_preserving() -> None:
    assert normalize_player_name("Vladímir Guerrero Jr.") == "vladimir guerrero jr"
    assert normalize_player_name("Jazz Chisholm Jr.") == "jazz chisholm jr"
