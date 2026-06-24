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
    assert payload["errors"] == []
