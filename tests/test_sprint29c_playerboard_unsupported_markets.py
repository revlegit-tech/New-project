from __future__ import annotations

from mlb_app.services import playerboard_builder as builder


def test_unsupported_markets_are_skipped_and_counted(monkeypatch) -> None:
    monkeypatch.setattr(
        builder,
        "load_saved_props",
        lambda *args, **kwargs: [
            {"date": "2026-06-24", "market": "batter_stolen_bases", "player": "Runner", "team": "LAD", "opponent": "SDP", "line": "0.5", "americanOdds": "-110"}
        ],
    )

    def explode(_row):
        raise AssertionError("unsupported market should not reach unified_prop_card")

    monkeypatch.setattr("mlb_app.domain.unified_prop_card.unified_prop_card", explode)
    monkeypatch.setattr(builder, "infer_missing_context", explode)

    payload = builder.build_playerboard(season=2026, date_label="2026-06-24", limit=10, save=False, source_mode="propline")

    assert payload["cardsBuilt"] == 0
    assert payload["skipped"]["unsupportedMarkets"]["batter_stolen_bases"] == 1
    assert payload["unsupportedMarketCounts"] == {"batter_stolen_bases": 1}
    assert payload["unsupportedMarketSamples"] == [
        {"player": "Runner", "market": "batter_stolen_bases", "side": "", "line": "0.5"}
    ]
    assert payload["errors"] == []


def test_unsupported_market_samples_are_capped_per_market(monkeypatch) -> None:
    monkeypatch.setattr(
        builder,
        "load_saved_props",
        lambda *args, **kwargs: [
            {
                "date": "2026-06-24",
                "market": "batter_stolen_bases",
                "player": f"Runner {i}",
                "team": "LAD",
                "opponent": "SDP",
                "line": "0.5",
                "americanOdds": "-110",
            }
            for i in range(12)
        ],
    )
    monkeypatch.setattr(builder, "infer_missing_context", lambda row, season: row)

    payload = builder.build_playerboard(season=2026, date_label="2026-06-24", limit=12, save=False, source_mode="propline")

    assert payload["unsupportedMarketCounts"]["batter_stolen_bases"] == 12
    assert len(payload["unsupportedMarketSamples"]) == 10


def test_research_only_rbi_market_does_not_raise_unsupported_model_error(monkeypatch) -> None:
    monkeypatch.setattr(
        builder,
        "load_saved_props",
        lambda *args, **kwargs: [
            {
                "date": "2026-06-24",
                "market": "batter_rbis",
                "player": "Run Producer",
                "team": "LAD",
                "opponent": "SDP",
                "line": "0.5",
                "americanOdds": "+120",
            }
        ],
    )

    def explode(_row):
        raise AssertionError("research-only RBI should not use unified_prop_card")

    monkeypatch.setattr("mlb_app.domain.unified_prop_card.unified_prop_card", explode)

    payload = builder.build_playerboard(season=2026, date_label="2026-06-24", limit=10, save=False, source_mode="propline")

    assert payload["errors"] == []
    assert payload["unsupportedMarketCounts"] == {}
    row = payload["top"][0]
    assert row["market"] == "batter_rbis"
    assert row["confidence"] == "Research only"
    assert row["finalProbabilityPercent"] is None
    assert row["finalEdgePercent"] is None
    assert row["betActionAllowed"] is False
