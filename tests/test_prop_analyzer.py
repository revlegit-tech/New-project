import unittest

import app
import mlb_prop_analyzer as analyzer


class PropAnalyzerTests(unittest.TestCase):
    def test_prop_odds_parser_handles_hr_and_pitcher_k_rows(self):
        props = analyzer.parse_prop_odds([app.ROOT / "examples" / "prop-odds-template.csv"])

        self.assertEqual(len(props), 2)
        self.assertEqual(props[0]["market"], "homeRuns")
        self.assertEqual(props[0]["odds"], 390)
        self.assertEqual(props[1]["market"], "pitcherStrikeouts")
        self.assertEqual(props[1]["line"], 5.5)

    def test_prop_rows_parser_supports_web_payloads(self):
        rows = [
            {"Market": "Home Run", "Player": "Aaron Judge", "Team": "NYY", "Opponent": "BOS", "Line": "0.5", "Odds": "+390"},
            {"Market": "Pitcher Strikeouts", "Pitcher": "Max Fried", "Team": "NYY", "Opponent": "BAL", "Line": "5.5", "Odds": "-115"},
        ]

        props = analyzer.parse_prop_rows(rows, "web")

        self.assertEqual(len(props), 2)
        self.assertEqual(props[0]["book"], "web")
        self.assertEqual(props[1]["player"], "Max Fried")

    def test_analyze_props_outputs_market_and_payout_columns(self):
        player = app.Player(
            player="Example Batter",
            team="NYY",
            league="AL",
            games=30,
            plate_appearances=130,
            at_bats=110,
            hits=33,
            doubles=8,
            triples=1,
            home_runs=8,
            walks=16,
            strikeouts=28,
            batting_average=0.300,
            on_base=0.385,
            slugging=0.610,
            ops=0.995,
            total_bases=67,
            player_id="example01",
        )
        data = analyzer.AnalyzerData(
            players=[player],
            opponents=[],
            game_logs=[
                {
                    "playerId": "example01",
                    "player": "Example Batter",
                    "opponent": "BOS",
                    "date": "2026-05-01",
                    "games": 1,
                    "plateAppearances": 4,
                    "atBats": 4,
                    "hits": 2,
                    "homeRuns": 1,
                    "totalBases": 5,
                }
            ],
            pitching_game_logs=[
                {
                    "pitcherId": "starter01",
                    "pitcher": "Example Starter",
                    "team": "NYY",
                    "opponent": "BOS",
                    "date": "2026-05-01",
                    "innings": 6.0,
                    "strikeouts": 7,
                    "battersFaced": 24,
                }
            ],
            team_game_logs=[],
            team_batting=[{"team": "BOS", "plateAppearances": 1000, "strikeouts": 260, "games": 28}],
            pitching=[
                {
                    "pitcher": "Example Starter",
                    "pitcherId": "starter01",
                    "team": "NYY",
                    "games": 7,
                    "gamesStarted": 7,
                    "innings": 40.0,
                    "strikeouts": 48,
                    "battersFaced": 162,
                    "walks": 10,
                    "era": 3.1,
                    "whip": 1.1,
                },
                {
                    "pitcher": "Example Opponent Starter",
                    "pitcherId": "starter02",
                    "team": "BOS",
                    "games": 7,
                    "gamesStarted": 7,
                    "innings": 39.0,
                    "strikeouts": 36,
                    "battersFaced": 160,
                    "homeRunsAllowed": 7,
                },
            ],
            batting_against=[],
            team_batting_against=[],
            team_advanced_pitching=[],
            player_advanced_pitching=[],
            team_standard_pitching=[],
            batter_pitcher_advanced=[],
        )
        games = [
            analyzer.ScheduleGame(
                game_id="1",
                away_team="BOS",
                home_team="NYY",
                away_probable_pitcher="Example Opponent Starter",
                home_probable_pitcher="Example Starter",
                venue="Example Park",
            )
        ]
        overrides = analyzer.ContextOverrides(
            weather_rows=[
                {
                    "Home Team": "NYY",
                    "Away Team": "BOS",
                    "Venue": "Example Park",
                    "Temperature": "76",
                    "Wind MPH": "8",
                    "Wind Direction": "out to center",
                    "_source": "test",
                }
            ]
        )
        props = [
            {"market": "homeRuns", "player": "Example Batter", "team": "NYY", "opponent": "BOS", "line": 0.5, "odds": 420, "book": "Book"},
            {"market": "pitcherStrikeouts", "player": "Example Starter", "team": "NYY", "opponent": "BOS", "line": 5.5, "odds": -115, "book": "Book"},
        ]

        rows, warnings = analyzer.analyze_props(props, data, games, overrides, recent_games=5)

        self.assertEqual(warnings, [])
        self.assertEqual(len(rows), 2)
        self.assertIn("model_probability", rows[0])
        self.assertIn("payout_$3", rows[0])
        self.assertGreater(rows[0]["payout_$20"], 20)

    def test_parlay_rows_combines_probabilities_and_returns(self):
        picks = [
            {"selection": "A over", "model_probability": 0.6, "odds": -110, "expected_value_per_unit": 0.1},
            {"selection": "B over", "model_probability": 0.5, "odds": 150, "expected_value_per_unit": 0.2},
        ]

        rows = analyzer.parlay_rows(picks, max_legs=2, pool_size=4, limit=5)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["model_probability"], 0.3)
        self.assertIn("payout_$10", rows[0])


if __name__ == "__main__":
    unittest.main()
