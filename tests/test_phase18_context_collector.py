from tools.phase18_fill_missing_context import wind_degrees_to_cardinal, norm_team


def test_wind_degrees_to_cardinal():
    assert wind_degrees_to_cardinal(0) == "N"
    assert wind_degrees_to_cardinal(90) == "E"
    assert wind_degrees_to_cardinal(180) == "S"
    assert wind_degrees_to_cardinal(270) == "W"


def test_norm_team_aliases():
    assert norm_team("SD") == "SDP"
    assert norm_team("SF") == "SFG"
    assert norm_team("WSH") == "WSN"
