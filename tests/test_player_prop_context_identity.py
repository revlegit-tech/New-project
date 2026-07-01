from __future__ import annotations

from mlb_app.services.player_prop_context_identity_service import (
    align_board_context_identity,
    clean_subject_name,
    normalize_player_name,
    normalize_team,
    subject_role_for_market,
)


def test_player_name_normalization_handles_suffixes_punctuation_and_accents() -> None:
    assert normalize_player_name("  JOSÉ   RAMÍREZ, Jr. ") == "jose ramirez"
    assert normalize_player_name("Ronald Acuña Jr.") == "ronald acuna"
    assert normalize_player_name("Mookie-Betts") == "mookie betts"
    assert normalize_player_name("O'Neil Cruz III") == "oneil cruz"
    assert normalize_player_name("Tanner Bibee Strikeouts Thrown") == "tanner bibee"
    assert normalize_player_name("Aaron Judge Over 0.5 Hits") == "aaron judge"


def test_team_normalization_handles_common_mlb_aliases() -> None:
    assert normalize_team("LA Dodgers") == "LAD"
    assert normalize_team("Los Angeles Dodgers") == "LAD"
    assert normalize_team("New York Yankees") == "NYY"
    assert normalize_team("New York Mets") == "NYM"
    assert normalize_team("Chicago White Sox") == "CHW"
    assert normalize_team("Chicago Cubs") == "CHC"
    assert normalize_team("Arizona Diamondbacks") == "ARI"
    assert normalize_team("Oakland Athletics") == "ATH"
    assert normalize_team("Athletics") == "ATH"


def test_subject_name_cleaning_removes_pitcher_suffix_only_for_pitcher_strikeouts() -> None:
    cleaned, warnings = clean_subject_name("Connelly Early Strikeouts Thrown", "pitcher_strikeouts")
    assert cleaned == "Connelly Early"
    assert warnings == ["subject_name_cleaned_from_market_label"]

    not_cleaned, no_warnings = clean_subject_name("Connelly Early Strikeouts Thrown", "batter_hits")
    assert not_cleaned == "Connelly Early Strikeouts Thrown"
    assert no_warnings == []


def test_subject_role_follows_supported_market_family() -> None:
    assert subject_role_for_market("batter_hits") == "batter"
    assert subject_role_for_market("pitcher_strikeouts") == "pitcher"
    assert subject_role_for_market("game_total") == "unknown"


def test_board_alignment_uses_explicit_team_and_infers_opponent_from_game_sides() -> None:
    row = align_board_context_identity(
        {
            "player": "Aaron Judge",
            "market": "batter_hits",
            "team": "New York Yankees",
            "homeTeam": "NYY",
            "awayTeam": "BOS",
        }
    )
    assert row["subjectRole"] == "batter"
    assert row["normalizedSubjectTeam"] == "NYY"
    assert row["normalizedSubjectOpponent"] == "BOS"


def test_board_alignment_does_not_guess_team_from_home_away_without_subject_team() -> None:
    row = align_board_context_identity(
        {"player": "Aaron Judge", "market": "batter_hits", "homeTeam": "NYY", "awayTeam": "BOS"}
    )
    assert row["normalizedSubjectTeam"] == ""
    assert row["normalizedSubjectOpponent"] == ""
    assert "skipped_unsafe_team_inference" in row["subjectIdentityWarnings"]


def test_board_alignment_fixes_reversed_team_only_with_explicit_subject_team_evidence() -> None:
    row = align_board_context_identity(
        {
            "player": "Tarik Skubal Strikeouts Thrown",
            "market": "pitcher_strikeouts",
            "playerTeam": "DET",
            "team": "HOU",
            "opponent": "DET",
            "homeTeam": "HOU",
            "awayTeam": "DET",
        }
    )
    assert row["subjectName"] == "Tarik Skubal"
    assert row["subjectRole"] == "pitcher"
    assert row["normalizedSubjectTeam"] == "DET"
    assert row["normalizedSubjectOpponent"] == "HOU"
    assert row["subjectTeamOpponentFixed"] is True
