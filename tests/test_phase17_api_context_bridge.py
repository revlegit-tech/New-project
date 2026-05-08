from tools.fetch_phase17_context_from_apis import (
    VENUE_COORD_REFERENCE,
    american_to_probability,
    canonical_team,
    game_key,
    implied_runs,
    parse_game_line_events,
)


def test_canonical_team_aliases():
    assert canonical_team("STL") == "st. louis cardinals"
    assert canonical_team("San Diego Padres") == "san diego padres"


def test_game_key_order_independent():
    assert game_key("STL", "SD") == game_key("San Diego Padres", "St. Louis Cardinals")


def test_american_probability():
    assert round(american_to_probability(-150), 4) == 0.6
    assert round(american_to_probability(120), 4) == 0.4545


def test_implied_runs_proxy():
    team, opp = implied_runs(8.0, -150, 130)
    assert team is not None and opp is not None
    assert round(team + opp, 3) == 8.0


def test_venue_coordinate_reference_has_common_venues():
    assert "yankee stadium" in VENUE_COORD_REFERENCE
    assert "petco park" in VENUE_COORD_REFERENCE


def test_parse_propline_style_game_lines():
    payload = [
        {
            "home_team": "San Diego Padres",
            "away_team": "St. Louis Cardinals",
            "commence_time": "2026-05-08T02:10:00Z",
            "bookmakers": [
                {
                    "key": "book_a",
                    "markets": [
                        {"key": "h2h", "outcomes": [{"name": "San Diego Padres", "price": -125}, {"name": "St. Louis Cardinals", "price": 110}]},
                        {"key": "totals", "outcomes": [{"name": "Over", "point": 8.5, "price": -110}, {"name": "Under", "point": 8.5, "price": -110}]},
                    ],
                }
            ],
        }
    ]
    lines, _, warnings = parse_game_line_events(payload, date="2026-05-07", source="propline_game_lines")
    assert not warnings
    line = lines[game_key("San Diego Padres", "St. Louis Cardinals")]
    assert line["home_team_moneyline"] == "-125.0"
    assert line["away_team_moneyline"] == "110.0"
    assert line["game_total"] == "8.5"
