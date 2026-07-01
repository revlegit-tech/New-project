from __future__ import annotations

from mlb_app.domain.unified_prop_context import all_data_predict
from mlb_app.services.playerboard_builder import aggregate_book_prices
from mlb_app.services.playerboard_service import _apply_selected_book


def _quote(book: str, odds: str) -> dict[str, object]:
    return {
        "date": "2026-06-24",
        "market": "batter_home_runs",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BOS",
        "line": "0.5",
        "rawLabel": "Over",
        "book": book,
        "bookKey": book.lower(),
        "americanOdds": odds,
        "lastUpdate": "2026-06-24T16:00:00Z",
    }


def test_aggregate_book_prices_preserves_quote_level_detail() -> None:
    rows = aggregate_book_prices([_quote("DraftKings", "+320"), _quote("FanDuel", "+340")])

    assert len(rows) == 1
    row = rows[0]
    assert row["bestBook"] == "FanDuel"
    assert row["bestAmericanOdds"] == "+340"
    assert row["quoteCount"] == 2
    assert row["availableBooks"] == ["FanDuel", "DraftKings"]
    assert [quote["book"] for quote in row["allBookQuotes"]] == ["FanDuel", "DraftKings"]


def test_second_aggregate_pass_keeps_existing_all_book_quotes() -> None:
    first_pass = aggregate_book_prices([_quote("DraftKings", "+320"), _quote("FanDuel", "+340")])
    second_pass = aggregate_book_prices(first_pass)

    assert len(second_pass) == 1
    assert second_pass[0]["quoteCount"] == 2
    assert [quote["book"] for quote in second_pass[0]["allBookQuotes"]] == ["FanDuel", "DraftKings"]


def test_selected_book_missing_quote_is_warning_not_fake_odds() -> None:
    payload = {"rows": aggregate_book_prices([_quote("DraftKings", "+320")])}

    selected = _apply_selected_book(payload, "FanDuel")["rows"][0]

    assert selected["selectedBook"] == "FanDuel"
    assert selected["selectedBookAmericanOdds"] is None
    assert selected["selectedBookImpliedProbability"] is None
    assert selected["selectedBookQuoteStatus"] == "no_quote_at_selected_book"
    assert any("No quote at selected book" in warning for warning in selected["trustWarnings"])


def test_missing_odds_do_not_default_to_minus_110_or_implied_probability() -> None:
    result = all_data_predict({
        "date": "2026-06-24",
        "market": "batter_hits",
        "player": "Test Player",
        "team": "NYY",
        "opponent": "BOS",
        "line": "0.5",
        "american_odds": "",
    })

    assert result["americanOdds"] is None
    assert result["sportsbookImpliedProbability"] is None
    assert result["sportsbookImpliedPercent"] is None
    assert result["edge"] is None
    assert result["edgePercent"] is None
