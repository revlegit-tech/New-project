from __future__ import annotations

from mlb_app.services.game_market_context_service import normalize_game_market_payload


def sample_payload(markets: list[dict]) -> dict:
    return {
        "events": [
            {
                "id": "evt1",
                "home_team": "LAD",
                "away_team": "SDP",
                "bookmakers": [{"key": "book", "markets": markets}],
            }
        ]
    }


def test_game_market_normalization_moneyline_h2h() -> None:
    rows, summary = normalize_game_market_payload(
        sample_payload([{"key": "h2h", "outcomes": [{"name": "LAD", "price": -140}, {"name": "SDP", "price": 120}]}]),
        date_label="2026-06-24",
        season=2026,
        source="the_odds_api",
    )

    assert summary["rowCount"] == 2
    assert {row["market"] for row in rows} == {"moneyline"}
    assert rows[0]["implied_probability"] != ""


def test_game_total_normalization() -> None:
    rows, _summary = normalize_game_market_payload(
        sample_payload([{"key": "totals", "outcomes": [{"name": "Over", "point": 8.5, "price": -110}, {"name": "Under", "point": 8.5, "price": -110}]}]),
        date_label="2026-06-24",
        season=2026,
    )

    assert {row["market"] for row in rows} == {"game_total"}
    assert {row["line"] for row in rows} == {"8.5"}


def test_spreads_normalize_to_run_line() -> None:
    rows, _summary = normalize_game_market_payload(
        sample_payload([{"key": "spreads", "outcomes": [{"name": "LAD", "point": -1.5, "price": 105}, {"name": "SDP", "point": 1.5, "price": -125}]}]),
        date_label="2026-06-24",
        season=2026,
    )

    assert {row["market"] for row in rows} == {"run_line"}
    assert {row["line"] for row in rows} == {"-1.5", "1.5"}


def test_team_totals_missing_is_partial_not_failure() -> None:
    rows, summary = normalize_game_market_payload(
        sample_payload([{"key": "h2h", "outcomes": [{"name": "LAD", "price": -140}, {"name": "SDP", "price": 120}]}]),
        date_label="2026-06-24",
        season=2026,
    )

    assert rows
    assert summary["status"] == "partial"
    assert summary["missingTeamTotalGames"] == 1
