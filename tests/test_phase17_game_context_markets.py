import json
from pathlib import Path

from tools.phase17_game_context_markets import (
    build_contexts,
    context_market_rows,
    enrich_playerboard_rows,
    parse_provider_game_lines,
)


def test_parse_provider_game_lines_merges_total_from_nested_market():
    payload = {
        "events": [
            {
                "id": "g1",
                "away_team": "Boston Red Sox",
                "home_team": "New York Yankees",
                "bookmakers": [
                    {
                        "title": "PropLine",
                        "markets": [
                            {"key": "h2h", "outcomes": [{"name": "Boston Red Sox", "price": 120}, {"name": "New York Yankees", "price": -140}]},
                            {"key": "totals", "outcomes": [{"name": "Over", "point": 8.5, "price": -110}, {"name": "Under", "point": 8.5, "price": -110}]},
                        ],
                    }
                ],
            }
        ]
    }
    games = parse_provider_game_lines(payload)
    assert len(games) == 1
    game = next(iter(games.values()))
    assert game.moneylines["boston red sox"] == 120
    assert game.moneylines["new york yankees"] == -140
    assert game.total == 8.5


def test_build_contexts_computes_implied_runs_only_with_total():
    payload = {"events": [{"away_team": "Boston Red Sox", "home_team": "New York Yankees", "markets": [{"key": "h2h", "outcomes": [{"name": "Boston Red Sox", "price": 120}, {"name": "New York Yankees", "price": -140}]}, {"key": "game total", "line": 8.5}]}]}
    games = parse_provider_game_lines(payload)
    rows = [{"date": "2026-05-07", "market": "batter_hits", "team": "BOS", "opponent": "NYY", "venue": "Yankee Stadium", "park_factor": "1.05", "weather_temperature_f": "68"}]
    contexts = build_contexts(rows, games, "2026-05-07", 2026, ["batter_hits"])
    assert len(contexts) == 1
    ctx = next(iter(contexts.values()))
    assert ctx.team_moneyline == "120"
    assert ctx.opponent_moneyline == "-140"
    assert ctx.game_total == "8.5"
    assert ctx.team_implied_runs
    assert ctx.opponent_implied_runs
    assert ctx.readiness == "ready"


def test_context_market_rows_include_missing_total_marker():
    payload = {"events": [{"away_team": "Boston Red Sox", "home_team": "New York Yankees", "markets": [{"key": "h2h", "outcomes": [{"name": "Boston Red Sox", "price": 120}, {"name": "New York Yankees", "price": -140}]}]}]}
    games = parse_provider_game_lines(payload)
    rows = [{"date": "2026-05-07", "market": "batter_hits", "team": "BOS", "opponent": "NYY"}]
    contexts = build_contexts(rows, games, "2026-05-07", 2026, ["batter_hits"])
    market_rows = context_market_rows(contexts)
    total_rows = [r for r in market_rows if r["market"] == "game_total"]
    assert total_rows
    assert total_rows[0]["readiness"] == "missing"


def test_enrich_playerboard_adds_context_markers():
    payload = {"events": [{"away_team": "Boston Red Sox", "home_team": "New York Yankees", "markets": [{"key": "h2h", "outcomes": [{"name": "Boston Red Sox", "price": 120}, {"name": "New York Yankees", "price": -140}]}, {"key": "total runs", "outcomes": [{"name": "Over 8.5", "price": -110}]}]}]}
    games = parse_provider_game_lines(payload)
    rows = [{"date": "2026-05-07", "market": "batter_hits", "team": "BOS", "opponent": "NYY"}]
    contexts = build_contexts(rows, games, "2026-05-07", 2026, ["batter_hits"])
    summary = enrich_playerboard_rows(rows, contexts, "2026-05-07", ["batter_hits"])
    assert summary["updatedRows"] == 1
    assert rows[0]["game_context_markets"] == "moneyline:ready;game_total:ready;implied_runs:ready"
    assert rows[0]["game_moneyline_market"] == "ready"
    assert rows[0]["game_total_market"] == "ready"
