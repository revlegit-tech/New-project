from __future__ import annotations

import sys
from typing import Any

from mlb_app.domain import team_game_markets
from mlb_app.services import playerboard_builder


def team_game_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-22",
        "market": "moneyline",
        "marketDisplay": "Moneyline - NYY",
        "originalMarket": "moneyline",
        "rawLabel": "NYY",
        "side": "NYY",
        "marketFamily": "team",
        "player": "NYY",
        "team": "NYY",
        "opponent": "BAL",
        "line": "0",
        "americanOdds": "-150",
        "bookmaker": "ExampleBook",
        "fixtureId": "fixture-1",
    }
    row.update(overrides)
    return row


def test_default_gate_off_does_not_import_or_call_legacy_predictor() -> None:
    sys.modules.pop("mlb_app.domain.team_game_market_predictor", None)

    row = team_game_markets.enrich_team_game_market_prediction(team_game_row())

    assert "mlb_app.domain.team_game_market_predictor" not in sys.modules
    assert row["sportsbookImpliedProbability"] == 0.6
    assert row["projectedProbability"] is None
    assert row["edge"] is None
    assert row["edgePercent"] is None
    assert row["finalEdgePercent"] is None
    assert row["modelName"] == ""
    assert row["modelAvailable"] is False


def test_explicit_gate_on_allows_legacy_predictor(monkeypatch) -> None:
    from mlb_app.domain import team_game_market_predictor

    calls: list[dict[str, Any]] = []

    def fake_predict(row: dict[str, Any], season: int = 2026) -> dict[str, Any]:
        calls.append({"row": row, "season": season})
        return {
            "projectedProbability": 0.62,
            "sportsbookImpliedProbability": 0.6,
            "edge": 0.02,
            "edgePercent": 2.0,
            "confidence": "Low",
            "modelName": "legacy_team_game_fixture",
            "modelAvailable": True,
        }

    monkeypatch.setattr(team_game_market_predictor, "predict_team_game_market", fake_predict)

    row = team_game_markets.enrich_team_game_market_prediction(
        team_game_row(date="2026-06-22T15:00:00Z"),
        projections_enabled=True,
    )

    assert calls and calls[0]["season"] == 2026
    assert row["projectedProbability"] == 0.62
    assert row["edge"] == 0.02
    assert row["edgePercent"] == 2.0
    assert row["finalEdgePercent"] == 2.0
    assert row["modelName"] == "legacy_team_game_fixture"
    assert row["modelAvailable"] is True


def test_playerboard_build_keeps_team_game_rows_odds_only_when_gate_off(monkeypatch) -> None:
    gated_row = team_game_markets.enrich_team_game_market_prediction(
        team_game_row(rawSource="fixture.csv"),
        projections_enabled=False,
    )
    monkeypatch.setattr(playerboard_builder, "load_saved_props", lambda *args, **kwargs: [gated_row])

    payload = playerboard_builder.build_playerboard(
        season=2026,
        date_label="2026-06-22",
        market="moneyline",
        limit=5,
        save=False,
    )

    assert payload["propsLoaded"] == 1
    assert payload["cardsBuilt"] == 1
    card = payload["top"][0]
    assert card["market"] == "moneyline"
    assert card["finalProbabilityPercent"] == 60.0
    assert card["sportsbookImpliedPercent"] == 60.0
    assert card["finalEdgePercent"] == 0.0
    assert card["confidence"] == "Unmodeled"
    assert card["recommendation"] == "Odds only"
    assert card["modelAvailable"] is False


def test_asgi_import_still_works() -> None:
    from mlb_app.asgi import app

    assert app is not None
