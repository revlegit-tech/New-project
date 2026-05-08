from tools.phase22_v3_fixture_metadata_fallback import _team_pair_key

def test_team_pair_aliases():
    assert _team_pair_key("SDP", "st louis cardinals") == _team_pair_key("San Diego Padres", "STL")
    assert _team_pair_key("ATH", "Baltimore Orioles") == _team_pair_key("oakland athletics", "BAL")
    assert _team_pair_key("WSN", "miami marlins") == _team_pair_key("Washington Nationals", "MIA")
