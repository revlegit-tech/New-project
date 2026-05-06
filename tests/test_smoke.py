import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest import mock

import app
import ml_prop_model
import odds_movement
import playerboard
import playerboard_backtest
import unified_prop_card


class PredictorSmokeTests(unittest.TestCase):
    def test_total_bases_prediction_includes_market_view(self):
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
            home_runs=6,
            walks=16,
            strikeouts=28,
            batting_average=0.300,
            on_base=0.385,
            slugging=0.555,
            ops=0.940,
            total_bases=61,
            player_id="example01",
        )

        payload = app.predict_prop(player, "BOS", 0, target="totalBases", line=1.5, odds=-110)

        self.assertEqual(payload["target"], "totalBases")
        self.assertIn("market", payload["prediction"])
        self.assertIn("probabilityOverLine", payload["prediction"])
        self.assertEqual(payload["prediction"]["market"]["odds"], -110)

    def test_market_view_converts_american_odds(self):
        market = app.market_view(0.57, 0.5, -110)

        self.assertEqual(market["odds"], -110)
        self.assertGreater(market["edge"], 0)
        self.assertIn(market["verdict"], {"Positive value", "Thin value", "Fair price"})

    def test_espn_team_entries_from_site_payload(self):
        payload = {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {
                                    "team": {
                                        "id": "10",
                                        "abbreviation": "NYY",
                                        "displayName": "New York Yankees",
                                        "shortDisplayName": "Yankees",
                                        "name": "Yankees",
                                        "location": "New York",
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        teams = [app.normalize_espn_team(team) for team in app.espn_team_entries(payload)]

        self.assertEqual(teams[0]["id"], "10")
        self.assertEqual(teams[0]["abbreviation"], "NYY")
        self.assertEqual(teams[0]["displayName"], "New York Yankees")

    def test_espn_event_normalization(self):
        event = {
            "id": "1",
            "name": "Away at Home",
            "shortName": "AWY @ HOM",
            "date": "2026-05-02T17:35Z",
            "competitions": [
                {
                    "venue": {"fullName": "Ballpark", "address": {"city": "Seattle"}},
                    "status": {"type": {"state": "post", "detail": "Final", "completed": True}},
                    "competitors": [
                        {"homeAway": "away", "score": "3", "team": {"abbreviation": "AWY", "displayName": "Away"}},
                        {
                            "homeAway": "home",
                            "score": "4",
                            "team": {"abbreviation": "HOM", "displayName": "Home"},
                            "probables": [
                                {
                                    "name": "probableStartingPitcher",
                                    "playerId": "99",
                                    "record": "2-1",
                                    "athlete": {"displayName": "Example Starter", "position": "SP"},
                                }
                            ],
                        },
                    ],
                }
            ],
        }

        normalized = app.normalize_espn_event(event)

        self.assertEqual(normalized["away"]["score"], 3)
        self.assertEqual(normalized["home"]["team"]["abbreviation"], "HOM")
        self.assertEqual(normalized["home"]["probableStarter"]["name"], "Example Starter")
        self.assertTrue(normalized["status"]["completed"])

    def test_html_table_to_csv_for_url_imports(self):
        raw = """
        <html><body><table>
          <tr><th>Player</th><th>Team</th><th>G</th><th>AB</th><th>H</th><th>BA</th></tr>
          <tr><td>Example Batter</td><td>NYY</td><td>10</td><td>30</td><td>9</td><td>.300</td></tr>
        </table></body></html>
        """

        rows = app.normalize_rows(app.html_table_to_csv(raw))

        self.assertEqual(rows[0]["Player"], "Example Batter")
        self.assertEqual(rows[0]["Team"], "NYY")
        self.assertEqual(rows[0]["BA"], ".300")

    def test_baseball_reference_commented_pitching_table(self):
        raw = """
        <html><body><div id="all_players_standard_pitching">
        <!--<table id="players_standard_pitching">
          <tr><th>Name</th><th>Team</th><th>G</th><th>GS</th><th>IP</th><th>H</th><th>BB</th><th>SO</th><th>ERA</th><th>WHIP</th></tr>
          <tr><td>Example Starter</td><td>NYY</td><td>5</td><td>5</td><td>28.1</td><td>20</td><td>6</td><td>31</td><td>2.86</td><td>0.92</td></tr>
        </table>-->
        </div></body></html>
        """

        csv_text = app.html_table_to_csv_by_id(raw, ["players_standard_pitching"])
        pitchers = app.parse_pitching(csv_text)

        self.assertEqual(pitchers[0]["pitcher"], "Example Starter")
        self.assertEqual(pitchers[0]["team"], "NYY")
        self.assertEqual(pitchers[0]["gamesStarted"], 5)
        self.assertEqual(pitchers[0]["strikeouts"], 31)

    def test_dataset_source_due_after_one_day(self):
        now = app.datetime(2026, 5, 3, 12, 0, tzinfo=app.timezone.utc)
        source = {"lastImportedAt": "2026-05-02T11:59:00+00:00"}

        self.assertTrue(app.dataset_source_due(source, now))
        self.assertFalse(app.dataset_source_due({"lastImportedAt": "2026-05-03T11:00:00+00:00"}, now))

    def test_fetch_dataset_url_blocks_local_network_hosts(self):
        with mock.patch.dict(os.environ, {"DATASET_URL_ALLOW_PRIVATE": "0", "DATASET_URL_ALLOWED_HOSTS": ""}):
            with self.assertRaisesRegex(ValueError, "private or local"):
                app.fetch_dataset_url("http://127.0.0.1:8766/stats.csv")

    def test_propline_props_save_uses_requested_date(self):
        class FakePropLineClient:
            def get_events(self, sport):
                return [
                    {"id": "event-1", "away_team": "BOS", "home_team": "NYY", "commence_time": "2026-05-03T20:00:00Z"},
                    {"id": "event-2", "away_team": "TOR", "home_team": "BAL", "commence_time": "2026-05-04T20:00:00Z"},
                ]

            def get_odds(self, sport, event_id, markets):
                return {
                    "bookmakers": [
                        {
                            "title": "Book",
                            "key": "book",
                            "markets": [
                                {
                                    "key": "batter_hits",
                                    "outcomes": [
                                        {"description": "Example Batter", "name": "Over", "point": 0.5, "price": -110}
                                    ],
                                }
                            ],
                        }
                    ]
                }

        saved = {}

        def fake_save(props, date_label):
            saved["date"] = date_label
            saved["count"] = len(props)
            return f"data/odds/propline_props_{date_label}.csv"

        with mock.patch("app.propline_client", lambda: FakePropLineClient()), mock.patch("app.save_propline_props_csv", fake_save):
            payload = app.propline_props_payload({"date": ["2026-05-03"], "markets": ["batter_hits"]})

        self.assertEqual(payload["date"], "2026-05-03")
        self.assertEqual(payload["eventCount"], 1)
        self.assertEqual(payload["totalEventCount"], 2)
        self.assertEqual(saved["date"], "2026-05-03")
        self.assertEqual(saved["count"], 1)

    def test_prop_model_paths_are_market_specific(self):
        self.assertEqual(
            ml_prop_model.model_path_for_market("pitcher_strikeouts").name,
            "prop_model_pitcher_strikeouts.joblib",
        )

    def test_unified_prop_card_reads_cloud_season_logs_when_local_cache_missing(self):
        cloud_rows = [
            {
                "player": "Example Batter",
                "team": "NYY",
                "date": "2026-05-03",
                "seasonPhase": "regular",
                "plateAppearances": "4",
                "atBats": "4",
                "hits": "2",
                "homeRuns": "1",
                "totalBases": "5",
                "strikeOuts": "1",
                "baseOnBalls": "0",
            }
        ]

        def fake_read_rows(path):
            return cloud_rows if str(path).startswith("cloud") else []

        with mock.patch.object(unified_prop_card, "CACHE_DIRS", [Path("incremental"), Path("season"), Path("cloud")]):
            with mock.patch.object(unified_prop_card, "read_rows", fake_read_rows):
                summary = unified_prop_card.summarize_batter("Example Batter", 2026)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["hits"], 2)
        self.assertEqual(summary["team"], "NYY")

    def test_odds_movement_uses_configurable_local_app_url(self):
        with mock.patch.dict(os.environ, {"BASEBALL_PROP_APP_URL": "http://127.0.0.1:8765/"}):
            self.assertEqual(odds_movement.local_app_base_url(), "http://127.0.0.1:8765")

    def test_mutating_action_endpoints_are_post_only(self):
        self.assertIn("/api/propline/props", app.POST_ONLY_ENDPOINTS)
        self.assertIn("/api/predictions/save", app.POST_ONLY_ENDPOINTS)

    def test_batting_imports_merge_by_player_and_team(self):
        saved_players = []
        first = app.parse_players("Name,Tm,G,PA,AB,H,BA,OPS\nExample Batter,NYY,10,40,35,10,.286,.800\n")
        second = app.parse_players("Player,Team,G,PA,AB,H,BA,OPS\nExample Batter,NYY,12,48,42,14,.333,.900\n")

        def fake_save(players):
            saved_players[:] = players

        with mock.patch("app.load_players", lambda: list(saved_players)), mock.patch("app.save_players", fake_save):
            app.merge_players(first)
            merged = app.merge_players(second)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].games, 12)
        self.assertEqual(merged[0].team, "NYY")
        self.assertEqual(merged[0].ops, 0.900)

    def test_game_log_matchup_aggregates_saved_sources(self):
        player = app.Player(
            player="Example Batter",
            team="NYY",
            league="AL",
            games=20,
            plate_appearances=80,
            at_bats=70,
            hits=21,
            doubles=4,
            triples=0,
            home_runs=3,
            walks=8,
            strikeouts=18,
            batting_average=0.300,
            on_base=0.360,
            slugging=0.485,
            ops=0.845,
            total_bases=34,
            player_id="example01",
        )
        logs = [
            {"sourceId": "one", "playerId": "example01", "player": "Example Batter", "opponent": "BOS", "games": 2, "atBats": 7, "hits": 3},
            {"sourceId": "two", "playerId": "example01", "player": "Example Batter", "opponent": "BOS", "games": 1, "atBats": 4, "hits": 2},
        ]

        adjustment, matchup = app.game_log_matchup(player, "BOS", logs)

        self.assertEqual(matchup["atBats"], 11)
        self.assertEqual(matchup["hits"], 5)
        self.assertEqual(matchup["sources"], 2)
        self.assertGreater(adjustment, 0)

    def test_pitching_game_logs_parse_and_summarize(self):
        raw = """Pitcher,Team,Opp,IP,H,ER,HR,BB,SO,BF
Example Starter,NYY,BOS,6.0,5,2,1,2,7,24
Example Starter,NYY,TOR,5.0,6,3,0,1,4,22
"""

        logs = app.parse_pitching_game_logs(raw)
        summary = app.pitching_game_log_summary({"pitcher": "Example Starter", "pitcherId": "", "team": "NYY"}, logs, "BOS")

        self.assertEqual(logs[0]["pitcher"], "Example Starter")
        self.assertEqual(logs[0]["opponent"], "BOS")
        self.assertEqual(logs[0]["strikeouts"], 7)
        self.assertAlmostEqual(summary["strikeoutRate"], 7 / 24)
        self.assertEqual(summary["games"], 1)

    def test_pitching_import_rejects_batting_rows(self):
        raw = """Player,Team,G,PA,AB,H,HR,BB,SO,BA,OPS
Example Hitter,NYY,30,120,100,30,8,12,20,.300,.900
Example Starter,NYY,6,0,0,0,0,10,38,0,0
"""

        pitchers = app.parse_pitching(raw)

        self.assertEqual(pitchers, [])

    def test_pitcher_options_merge_by_name_team_when_ids_arrive_later(self):
        standard = [{"pitcher": "Example Starter", "pitcherId": "", "team": "NYY", "innings": 30.0, "gamesStarted": 5, "era": 3.0}]
        advanced = [{"pitcher": "Example Starter", "pitcherId": "starter01", "team": "NYY", "innings": 30.0, "strikeoutRate": 0.25}]

        with mock.patch("app.load_pitching", lambda: standard), mock.patch("app.load_batting_against", lambda: []), mock.patch("app.load_player_advanced_pitching", lambda: advanced):
            options = app.load_pitcher_options()

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["pitcherId"], "starter01")
        self.assertAlmostEqual(options[0]["strikeoutRate"], 0.25)

    def test_team_game_logs_parse_results_and_matchup_summary(self):
        raw = """,Score,Batting Stats,Opp Starter
Rk,Gtm,Date,,Opp,Rslt,RS,RA,Inn,PA,AB,R,H,2B,3B,HR,RBI,SB,CS,BB,SO,BA,OBP,SLG,OPS,TB,GIDP,HBP,SH,SF,ROE,IBB,BAbip,LOB,#,Player,T,GmSc
1,1,2026-03-26,@,LAD,L,2,8,9,31,31,2,6,1,0,1,2,0,1,0,8,.194,.194,.323,.516,10,0,0,0,0,0,0,.227,2,9,Yoshinobu Yamamoto,R,60
2,2,2026-03-30,,LAD,W,6,3,9,39,35,6,11,2,0,2,6,0,0,4,7,.314,.385,.543,.928,19,0,0,0,0,0,0,.360,7,9,Tyler Glasnow,R,42
"""

        logs = app.parse_team_game_logs(raw, "ARI")

        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["team"], "ARI")
        self.assertEqual(logs[0]["opponent"], "LAD")
        self.assertFalse(logs[0]["win"])
        self.assertEqual(logs[1]["opposingPitcher"], "Tyler Glasnow")

        with mock.patch("app.load_team_game_logs", lambda: logs):
            summary = app.team_matchup_summary("ARI", "LAD")

        self.assertEqual(summary["direct"]["games"], 2)
        self.assertEqual(summary["direct"]["wins"], 1)
        self.assertEqual(summary["direct"]["losses"], 1)
        self.assertAlmostEqual(summary["direct"]["winRate"], 0.5)

    def test_batter_recent_form_includes_last_five_vs_opponent_rows(self):
        player = app.Player(
            player="Example Batter",
            team="NYY",
            league="AL",
            games=20,
            plate_appearances=80,
            at_bats=70,
            hits=21,
            doubles=4,
            triples=0,
            home_runs=3,
            walks=8,
            strikeouts=18,
            batting_average=0.300,
            on_base=0.360,
            slugging=0.485,
            ops=0.845,
            total_bases=34,
            player_id="example01",
        )
        logs = [
            {
                "playerId": "example01",
                "player": "Example Batter",
                "opponent": "",
                "entries": [
                    {"date": "2026-05-01", "opponent": "BOS", "plateAppearances": 4, "atBats": 4, "hits": 2, "homeRuns": 1, "strikeouts": 1, "totalBases": 5},
                    {"date": "2026-04-20", "opponent": "BOS", "plateAppearances": 4, "atBats": 4, "hits": 1, "homeRuns": 0, "strikeouts": 2, "totalBases": 1},
                    {"date": "2026-04-18", "opponent": "TOR", "plateAppearances": 4, "atBats": 4, "hits": 0, "homeRuns": 0, "strikeouts": 1, "totalBases": 0},
                ],
            }
        ]

        recent = app.batter_recent_form(player, "BOS", logs)

        self.assertEqual(len(recent["last5VsOpponentEntries"]), 2)
        self.assertEqual(recent["last5VsOpponentEntries"][0]["date"], "2026-05-01")
        self.assertEqual(recent["last5VsOpponent"]["hits"], 3)

    def test_statcast_summary_derives_quality_metrics(self):
        rows = [
            {
                "events": "single",
                "description": "hit_into_play",
                "launch_speed": "101.2",
                "launch_angle": "18",
                "launch_speed_angle": "6",
                "woba_value": "0.9",
                "woba_denom": "1",
                "estimated_woba_using_speedangle": ".720",
                "estimated_ba_using_speedangle": ".650",
                "estimated_slg_using_speedangle": "1.200",
            },
            {
                "events": "strikeout",
                "description": "swinging_strike",
                "woba_value": "0",
                "woba_denom": "1",
            },
            {
                "events": "walk",
                "description": "ball",
                "woba_value": "0.7",
                "woba_denom": "1",
            },
        ]

        summary = app.summarize_statcast_rows(rows, "sample")

        self.assertEqual(summary["plateAppearances"], 3)
        self.assertEqual(summary["hits"], 1)
        self.assertEqual(summary["strikeouts"], 1)
        self.assertEqual(summary["barrels"], 1)
        self.assertAlmostEqual(summary["barrelRate"], 1.0)
        self.assertAlmostEqual(summary["hardHitRate"], 1.0)
        self.assertAlmostEqual(summary["whiffRate"], 0.5)
        self.assertAlmostEqual(summary["woba"], 0.533)

    def test_ballpark_context_parses_weather_and_factors(self):
        raw = """Date,Home Team,Away Team,Venue,Temperature,Wind MPH,Wind Direction,Roof,Park Factor,HR Factor,Hit Factor,Source
2026-05-03,NYY,BOS,Yankee Stadium,78,12,out to right,open,108,112,103,BallparkPal
"""

        rows = app.parse_ballpark_context(raw)
        environment = app.ballpark_environment_context("NYY", "BOS", "2026-05-03")

        self.assertEqual(rows[0]["homeTeam"], "NYY")
        self.assertAlmostEqual(rows[0]["parkFactor"], 1.08)
        with mock.patch("app.load_ballpark_context", lambda: rows), mock.patch("app.load_game_context", lambda: []):
            environment = app.ballpark_environment_context("NYY", "BOS", "2026-05-03")

        self.assertTrue(environment["available"])
        self.assertEqual(environment["venue"], "Yankee Stadium")
        self.assertGreater(environment["homeRunFactor"], 1.1)

    def test_prediction_blends_saved_statcast_and_environment_context(self):
        player = app.Player(
            player="Example Batter",
            team="NYY",
            league="AL",
            games=30,
            plate_appearances=120,
            at_bats=100,
            hits=25,
            doubles=5,
            triples=0,
            home_runs=4,
            walks=10,
            strikeouts=24,
            batting_average=0.250,
            on_base=0.330,
            slugging=0.420,
            ops=0.750,
            total_bases=42,
            player_id="example01",
        )
        statcast = [
            {
                "playerId": "example01",
                "player": "Example Batter",
                "role": "batter",
                "season": 2026,
                "endDate": "2026-05-03",
                "plateAppearances": 80,
                "xba": 0.310,
                "xslg": 0.600,
                "xwoba": 0.410,
                "barrelRate": 0.12,
                "hardHitRate": 0.48,
                "strikeoutRate": 0.20,
            }
        ]
        rolling = [
            {
                "playerId": "example01",
                "player": "Example Batter",
                "role": "batter",
                "season": 2026,
                "windowDays": 7,
                "plateAppearances": 20,
                "xwoba": 0.430,
                "battingAverage": 0.320,
                "barrelRate": 0.14,
                "hardHitRate": 0.50,
                "strikeoutRate": 0.18,
            }
        ]
        ballpark = app.parse_ballpark_context(
            "Date,Home Team,Away Team,Venue,Temperature,Wind MPH,Wind Direction,Roof,Park Factor,HR Factor,Hit Factor\n"
            "2026-05-03,NYY,BOS,Yankee Stadium,78,12,out to right,open,108,112,103\n"
        )

        patches = [
            mock.patch("app.load_statcast_quality", lambda: statcast),
            mock.patch("app.load_rolling_form", lambda: rolling),
            mock.patch("app.load_handedness_splits", lambda: []),
            mock.patch("app.load_ballpark_context", lambda: ballpark),
            mock.patch("app.load_game_context", lambda: []),
            mock.patch("app.load_opponents", lambda: []),
            mock.patch("app.load_team_batting_against", lambda: []),
            mock.patch("app.load_team_standard_pitching", lambda: []),
            mock.patch("app.load_team_advanced_pitching", lambda: []),
            mock.patch("app.load_game_logs", lambda: []),
            mock.patch("app.load_pitcher_options", lambda: []),
            mock.patch("app.load_pitching_game_logs", lambda: []),
            mock.patch("app.load_team_batting", lambda: []),
            mock.patch("app.load_team_game_logs", lambda: []),
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12], patches[13]:
            payload = app.predict_prop(player, "BOS", 0, target="homeRuns", line=0.5, odds=-110, date="2026-05-03")

        self.assertTrue(payload["opponent"]["environment"]["available"])
        self.assertGreater(payload["inputs"]["environmentHomeRunFactor"], 1.1)
        self.assertGreater(payload["opponent"]["advancedBatterAdjustment"], 0)

    def test_mlb_batter_game_log_splits_normalize_to_saved_entries(self):
        splits = [
            {
                "date": "2026-05-01",
                "opponent": {"abbreviation": "BOS"},
                "stat": {
                    "atBats": "4",
                    "hits": "2",
                    "homeRuns": "1",
                    "baseOnBalls": "1",
                    "strikeOuts": "1",
                    "totalBases": "5",
                },
            }
        ]

        entries = app.batter_game_log_entries_from_splits(splits)
        summary = app.summarize_batter_game_log_record(entries)

        self.assertEqual(entries[0]["opponent"], "BOS")
        self.assertEqual(entries[0]["plateAppearances"], 5)
        self.assertEqual(summary["homeRuns"], 1)
        self.assertAlmostEqual(summary["slugging"], 1.25)

    def test_mlb_pitching_game_log_splits_normalize_innings(self):
        splits = [
            {
                "date": "2026-05-01",
                "opponent": {"abbreviation": "BOS"},
                "stat": {
                    "inningsPitched": "5.2",
                    "hits": "4",
                    "runs": "2",
                    "earnedRuns": "2",
                    "homeRuns": "1",
                    "baseOnBalls": "1",
                    "strikeOuts": "7",
                    "battersFaced": "23",
                },
            }
        ]

        records = app.pitching_game_log_records_from_splits(splits, "Example Starter", "starter01", 123, 2026)

        self.assertEqual(records[0]["opponent"], "BOS")
        self.assertAlmostEqual(records[0]["innings"], 5 + 2 / 3)
        self.assertEqual(records[0]["strikeouts"], 7)
        self.assertEqual(records[0]["pitcherId"], "starter01")

    def test_source_capability_map_lists_refreshable_model_gaps(self):
        capabilities = app.source_capability_map()["capabilities"]
        needs = {item["need"] for item in capabilities}

        self.assertIn("Advanced batter-vs-pitcher matchups", needs)
        self.assertIn("Pitch arsenal and pitch-type performance", needs)
        self.assertIn("Statcast quality metrics", needs)
        self.assertIn("Weather-adjusted park environment", needs)


class PlayerboardReliabilityTests(unittest.TestCase):
    def test_playerboard_ladder_hit_prop_normalizes_without_shift(self):
        row = {
            "date": "2026-05-04",
            "market": "batter_hits",
            "player": "Juan Soto",
            "team": "NYY",
            "opponent": "BAL",
            "pitcher": "Example Starter",
            "side": "4+ Hits",
            "americanOdds": "2500",
        }

        prop = playerboard.normalize_prop_row(row, "2026-05-04")

        self.assertEqual(prop["player"], "Juan Soto")
        self.assertEqual(prop["market"], "batter_hits_alt")
        self.assertEqual(prop["marketDisplay"], "Batter Hits Ladder - 4+ Hits")
        self.assertEqual(prop["baseMarket"] if "baseMarket" in prop else playerboard.base_market(prop["market"]), "batter_hits")
        self.assertEqual(prop["line"], "3.5")
        self.assertEqual(prop["team"], "NYY")
        self.assertEqual(prop["opponent"], "BAL")
        self.assertEqual(prop["rawLabel"], "4+ Hits")

    def test_playerboard_schema_guard_rotates_old_csv_header(self):
        old_dir = playerboard.PLAYERBOARD_DIR

        with tempfile.TemporaryDirectory() as tmp:
            playerboard.PLAYERBOARD_DIR = Path(tmp)
            playerboard._CSV_CACHE.clear()
            playerboard._SAVED_PLAYERBOARD_CACHE.clear()

            try:
                path = playerboard.playerboard_file(2026)
                path.parent.mkdir(parents=True, exist_ok=True)

                # Old schema intentionally missing marketDisplay/baseMarket/isAltMarket.
                path.write_text(
                    "snapshotAt,season,date,market,player,team,opponent,line,americanOdds\n"
                    "old,2026,2026-05-04,batter_hits,Example Player,NYY,BAL,0.5,-110\n",
                    encoding="utf-8",
                )

                card = {
                    "market": "batter_hits_alt",
                    "marketDisplay": "Batter Hits Ladder - 4+ Hits",
                    "baseMarket": "batter_hits",
                    "isAltMarket": True,
                    "player": "Juan Soto",
                    "team": "NYY",
                    "opponent": "BAL",
                    "pitcher": "Example Starter",
                    "line": "3.5",
                    "americanOdds": "2500",
                    "finalProbabilityPercent": "8.5",
                    "sportsbookImpliedPercent": "3.85",
                    "finalEdgePercent": "4.65",
                    "confidence": "Low",
                    "recommendation": "Alt ladder market",
                    "weatherAdjustmentPercent": "0",
                    "savantAdjustmentPercent": "0",
                    "oddsMovementAdjustmentPercent": "0",
                    "missingData": [],
                    "originalMarket": "batter_hits",
                    "rawLabel": "4+ Hits",
                    "marketFamily": "batter",
                }

                playerboard.save_playerboard_snapshot(2026, "2026-05-04", [card])

                header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
                self.assertEqual(header, playerboard.PLAYERBOARD_FIELDS)

                rotated = list(Path(tmp).glob("playerboard_2026.header_mismatch_*.csv"))
                self.assertEqual(len(rotated), 1)

                saved_rows = playerboard.read_csv_rows(path)
                self.assertEqual(saved_rows[0]["player"], "Juan Soto")
                self.assertEqual(saved_rows[0]["market"], "batter_hits_alt")
                self.assertEqual(saved_rows[0]["marketDisplay"], "Batter Hits Ladder - 4+ Hits")
                self.assertEqual(saved_rows[0]["team"], "NYY")
                self.assertEqual(saved_rows[0]["opponent"], "BAL")
            finally:
                playerboard.PLAYERBOARD_DIR = old_dir
                playerboard._CSV_CACHE.clear()
                playerboard._SAVED_PLAYERBOARD_CACHE.clear()

    def test_playerboard_health_payload_reports_schema_and_shifted_rows(self):
        old_dir = playerboard.PLAYERBOARD_DIR

        with tempfile.TemporaryDirectory() as tmp:
            playerboard.PLAYERBOARD_DIR = Path(tmp)
            playerboard._CSV_CACHE.clear()
            playerboard._SAVED_PLAYERBOARD_CACHE.clear()

            try:
                card = {
                    "market": "batter_hits_alt",
                    "marketDisplay": "Batter Hits Ladder - 4+ Hits",
                    "baseMarket": "batter_hits",
                    "isAltMarket": True,
                    "player": "Juan Soto",
                    "team": "NYY",
                    "opponent": "BAL",
                    "pitcher": "Example Starter",
                    "line": "3.5",
                    "americanOdds": "2500",
                    "finalProbabilityPercent": "8.5",
                    "sportsbookImpliedPercent": "3.85",
                    "finalEdgePercent": "4.65",
                    "confidence": "Low",
                    "recommendation": "Alt ladder market",
                    "weatherAdjustmentPercent": "0",
                    "savantAdjustmentPercent": "0",
                    "oddsMovementAdjustmentPercent": "0",
                    "missingData": [],
                    "originalMarket": "batter_hits",
                    "rawLabel": "4+ Hits",
                    "marketFamily": "batter",
                }

                playerboard.save_playerboard_snapshot(2026, "2026-05-04", [card])

                payload = app.playerboard_health_payload({
                    "season": ["2026"],
                    "date": ["2026-05-04"],
                })

                self.assertTrue(payload["schemaOk"])
                self.assertEqual(payload["schemaIssue"], "")
                self.assertEqual(payload["rowsLoaded"], 1)
                self.assertEqual(payload["missingMarketDisplayRows"], 0)
                self.assertEqual(payload["badShiftedRows"], 0)
                self.assertEqual(payload["marketsPresent"]["batter_hits_alt"], 1)
                self.assertEqual(payload["schemaVersion"], "PLAYERBOARD_FIELDS_v2")
            finally:
                playerboard.PLAYERBOARD_DIR = old_dir
                playerboard._CSV_CACHE.clear()
                playerboard._SAVED_PLAYERBOARD_CACHE.clear()

    def test_playerboard_health_payload_defaults_to_latest_saved_date(self):
        old_dir = playerboard.PLAYERBOARD_DIR

        with tempfile.TemporaryDirectory() as tmp:
            playerboard.PLAYERBOARD_DIR = Path(tmp)
            playerboard._CSV_CACHE.clear()
            playerboard._SAVED_PLAYERBOARD_CACHE.clear()

            try:
                card = {
                    "market": "batter_hits_alt",
                    "marketDisplay": "Batter Hits Ladder - 4+ Hits",
                    "baseMarket": "batter_hits",
                    "isAltMarket": True,
                    "player": "Juan Soto",
                    "team": "NYY",
                    "opponent": "BAL",
                    "pitcher": "Example Starter",
                    "line": "3.5",
                    "americanOdds": "2500",
                    "finalProbabilityPercent": "8.5",
                    "sportsbookImpliedPercent": "3.85",
                    "finalEdgePercent": "4.65",
                    "confidence": "Low",
                    "recommendation": "Alt ladder market",
                    "weatherAdjustmentPercent": "0",
                    "savantAdjustmentPercent": "0",
                    "oddsMovementAdjustmentPercent": "0",
                    "missingData": [],
                    "originalMarket": "batter_hits",
                    "rawLabel": "4+ Hits",
                    "marketFamily": "batter",
                }

                playerboard.save_playerboard_snapshot(2026, "2026-05-04", [card])

                payload = app.playerboard_health_payload({
                    "season": ["2026"],
                })

                self.assertEqual(payload["date"], "2026-05-04")
                self.assertEqual(payload["latestAvailableDate"], "2026-05-04")
                self.assertEqual(payload["rowsLoaded"], 1)
                self.assertTrue(payload["ok"])
            finally:
                playerboard.PLAYERBOARD_DIR = old_dir
                playerboard._CSV_CACHE.clear()
                playerboard._SAVED_PLAYERBOARD_CACHE.clear()

    def test_playerboard_backtest_prefers_warehouse_logs_over_incremental_cache(self):
        old_stats = playerboard_backtest.STATS_DIR
        old_warehouse = playerboard_backtest.SEASON_LOG_DIR
        old_cloud = playerboard_backtest.CLOUD_SEASON_LOG_DIR

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            playerboard_backtest.STATS_DIR = base / "incremental"
            playerboard_backtest.SEASON_LOG_DIR = base / "warehouse"
            playerboard_backtest.CLOUD_SEASON_LOG_DIR = base / "cloud"

            try:
                playerboard_backtest.STATS_DIR.mkdir(parents=True, exist_ok=True)
                playerboard_backtest.SEASON_LOG_DIR.mkdir(parents=True, exist_ok=True)

                # Stale incremental cache has the same file but should not win.
                (playerboard_backtest.STATS_DIR / "batter_game_logs_2026.csv").write_text(
                    "date,player,team,hits,source\n"
                    "2026-05-04,Juan Soto,NYY,0,incremental\n",
                    encoding="utf-8",
                )

                # Fresh warehouse logs should be preferred.
                (playerboard_backtest.SEASON_LOG_DIR / "batter_game_logs_2026.csv").write_text(
                    "date,player,team,hits,source\n"
                    "2026-05-04,Juan Soto,NYY,2,warehouse\n",
                    encoding="utf-8",
                )

                rows = playerboard_backtest.batter_logs(2026)

                self.assertEqual(rows[0]["source"], "warehouse")
                self.assertEqual(rows[0]["hits"], "2")
            finally:
                playerboard_backtest.STATS_DIR = old_stats
                playerboard_backtest.SEASON_LOG_DIR = old_warehouse
                playerboard_backtest.CLOUD_SEASON_LOG_DIR = old_cloud

    def test_grading_health_payload_reads_latest_summary(self):
        old_data_dir = app.DATA_DIR

        with tempfile.TemporaryDirectory() as tmp:
            app.DATA_DIR = Path(tmp)
            health_dir = app.DATA_DIR / "health"
            health_dir.mkdir(parents=True, exist_ok=True)
            latest = health_dir / "latest_grading_summary.json"
            latest.write_text(
                json.dumps({
                    "checkedAt": "2026-05-05T09:00:00+00:00",
                    "date": "2026-05-04",
                    "season": 2026,
                    "ok": True,
                    "counts": {
                        "backtestRowsForDate": 10,
                        "gradedBacktestRowsForDate": 8,
                        "mlRowsForDate": 10,
                        "gradedMlRowsForDate": 8,
                        "backtestResultsForDate": {"win": 4, "loss": 4, "ungraded": 2},
                        "mlResultsForDate": {"win": 4, "loss": 4, "ungraded": 2},
                    },
                    "warnings": [],
                    "errors": [],
                }),
                encoding="utf-8",
            )

            try:
                payload = app.grading_health_payload({"date": ["2026-05-04"]})

                self.assertTrue(payload["exists"])
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["date"], "2026-05-04")
                self.assertEqual(payload["summary"]["backtestRowsForDate"], 10)
                self.assertEqual(payload["summary"]["gradedBacktestRowsForDate"], 8)
                self.assertEqual(payload["summary"]["mlRowsForDate"], 10)
                self.assertEqual(payload["summary"]["gradedMlRowsForDate"], 8)
            finally:
                app.DATA_DIR = old_data_dir

    def test_workflow_summaries_payload_reads_latest_files(self):
        old_data_dir = app.DATA_DIR

        with tempfile.TemporaryDirectory() as tmp:
            app.DATA_DIR = Path(tmp)
            health_dir = app.DATA_DIR / "health"
            health_dir.mkdir(parents=True, exist_ok=True)

            for filename, date_label in [
                ("latest_daily_health.json", "2026-05-04"),
                ("latest_grading_summary.json", "2026-05-04"),
                ("latest_weekly_repair.json", "2026-05-04"),
            ]:
                (health_dir / filename).write_text(
                    json.dumps({
                        "checkedAt": "2026-05-05T09:00:00+00:00",
                        "date": date_label,
                        "season": 2026,
                        "ok": True,
                        "warnings": [],
                        "errors": [],
                    }),
                    encoding="utf-8",
                )

            try:
                payload = app.workflow_summaries_payload({})

                self.assertTrue(payload["ok"])
                self.assertTrue(payload["summaries"]["dailyHealth"]["exists"])
                self.assertTrue(payload["summaries"]["dailyGrading"]["exists"])
                self.assertTrue(payload["summaries"]["weeklyRepair"]["exists"])
                self.assertEqual(payload["summaries"]["dailyHealth"]["date"], "2026-05-04")
            finally:
                app.DATA_DIR = old_data_dir

    def test_app_status_payload_reports_compact_health(self):
        old_data_dir = app.DATA_DIR
        old_playerboard_dir = playerboard.PLAYERBOARD_DIR

        with tempfile.TemporaryDirectory() as tmp:
            app.DATA_DIR = Path(tmp)
            playerboard.PLAYERBOARD_DIR = app.DATA_DIR / "playerboard"
            playerboard.PLAYERBOARD_DIR.mkdir(parents=True, exist_ok=True)

            health_dir = app.DATA_DIR / "health"
            health_dir.mkdir(parents=True, exist_ok=True)
            (health_dir / "latest_grading_summary.json").write_text(
                json.dumps({
                    "checkedAt": "2026-05-05T09:00:00+00:00",
                    "date": "2026-05-04",
                    "season": 2026,
                    "ok": True,
                    "counts": {
                        "backtestRowsForDate": 10,
                        "gradedBacktestRowsForDate": 8,
                        "mlRowsForDate": 10,
                        "gradedMlRowsForDate": 8,
                    },
                    "warnings": [],
                    "errors": [],
                }),
                encoding="utf-8",
            )

            (health_dir / "latest_daily_health.json").write_text(
                json.dumps({
                    "checkedAt": "2026-05-05T09:00:00+00:00",
                    "date": "2026-05-04",
                    "season": 2026,
                    "ok": True,
                    "warnings": [],
                    "errors": [],
                }),
                encoding="utf-8",
            )

            card = {
                "market": "batter_hits",
                "marketDisplay": "Batter Hits",
                "baseMarket": "batter_hits",
                "isAltMarket": False,
                "player": "Aaron Judge",
                "team": "NYY",
                "opponent": "BAL",
                "pitcher": "Shane Baz",
                "line": "1.5",
                "americanOdds": "-110",
                "finalProbabilityPercent": "58.7",
                "sportsbookImpliedPercent": "52.4",
                "finalEdgePercent": "6.3",
                "confidence": "Medium",
                "recommendation": "Positive edge",
                "weatherAdjustmentPercent": "0",
                "savantAdjustmentPercent": "0",
                "oddsMovementAdjustmentPercent": "0",
                "missingData": [],
                "originalMarket": "batter_hits",
                "rawLabel": "Hits",
                "marketFamily": "batter",
            }

            try:
                playerboard.save_playerboard_snapshot(2026, "2026-05-04", [card])
                payload = app.app_status_payload({"season": ["2026"]})

                self.assertIn("playerboard", payload)
                self.assertIn("grading", payload)
                self.assertIn("workflows", payload)
                self.assertEqual(payload["playerboard"]["date"], "2026-05-04")
                self.assertEqual(payload["grading"]["gradedBacktestRowsForDate"], 8)
            finally:
                app.DATA_DIR = old_data_dir
                playerboard.PLAYERBOARD_DIR = old_playerboard_dir
                playerboard._CSV_CACHE.clear()
                playerboard._SAVED_PLAYERBOARD_CACHE.clear()



if __name__ == "__main__":
    unittest.main()
