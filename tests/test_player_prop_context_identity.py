from __future__ import annotations

from mlb_app.services.player_prop_context_identity_service import normalize_player_name, normalize_team


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
