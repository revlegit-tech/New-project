from __future__ import annotations

from scripts.benchmark_playerboard_builder import benchmark_warning
from mlb_app.services import playerboard_builder as builder


def test_builder_respects_requested_limit_and_includes_timings_performance(monkeypatch) -> None:
    props = [
        {"date": "2026-06-24", "market": "batter_hits", "player": f"Player {i}", "team": "LAD", "opponent": "SDP", "line": "0.5", "americanOdds": "-110"}
        for i in range(5)
    ]
    monkeypatch.setattr(builder, "load_saved_props", lambda *args, **kwargs: props[: kwargs.get("limit", 5)])

    def fake_card(row):
        return {
            "player": row["player"],
            "market": row["market"],
            "team": row["team"],
            "opponent": row["opponent"],
            "line": row["line"],
            "americanOdds": row["american_odds"],
            "finalEdgePercent": 1,
        }

    monkeypatch.setattr("mlb_app.domain.unified_prop_card.unified_prop_card", fake_card)

    payload = builder.build_playerboard(season=2026, date_label="2026-06-24", limit=3, save=False, source_mode="propline")

    assert payload["propsLoaded"] == 3
    assert payload["cardsBuilt"] == 3
    assert {
        "loadPropsMs",
        "buildCardsMs",
        "marketFilterMs",
        "unifiedPropCardMs",
        "hitProfileMs",
        "historyLookupMs",
        "contextJoinMs",
        "cardPostProcessMs",
        "aggregateMs",
        "saveMs",
        "totalMs",
    } <= set(payload["timings"])
    assert {
        "cacheHits",
        "cacheMisses",
        "hitProfileCacheHits",
        "hitProfileCacheMisses",
        "historyCacheHits",
        "historyCacheMisses",
        "contextCacheHits",
        "contextCacheMisses",
    } <= set(payload)
    assert payload["performance"]["loadLimit"] == 3
    assert payload["performance"]["workers"] >= 1


def test_repeated_rows_hit_unified_and_hit_profile_cache(monkeypatch) -> None:
    repeated = {"date": "2026-06-24", "market": "batter_hits", "player": "Same Player", "team": "LAD", "opponent": "SDP", "line": "0.5", "americanOdds": "-110"}
    monkeypatch.setattr(builder, "load_saved_props", lambda *args, **kwargs: [dict(repeated), dict(repeated)])

    calls = {"card": 0}

    def fake_card(row):
        calls["card"] += 1
        return {
            "player": row["player"],
            "market": row["market"],
            "team": row["team"],
            "opponent": row["opponent"],
            "line": row["line"],
            "americanOdds": row["american_odds"],
            "finalEdgePercent": 1,
        }

    monkeypatch.setattr("mlb_app.domain.unified_prop_card.unified_prop_card", fake_card)

    payload = builder.build_playerboard(season=2026, date_label="2026-06-24", limit=2, save=False, source_mode="propline")

    assert calls["card"] == 1
    assert payload["cacheHits"] >= 1
    assert payload["hitProfileCacheHits"] >= 1


def test_no_save_does_not_write_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        builder,
        "load_saved_props",
        lambda *args, **kwargs: [
            {"date": "2026-06-24", "market": "batter_hits", "player": "Player", "team": "LAD", "opponent": "SDP", "line": "0.5", "americanOdds": "-110"}
        ],
    )
    monkeypatch.setattr("mlb_app.domain.unified_prop_card.unified_prop_card", lambda row: {"player": row["player"], "market": row["market"], "team": row["team"], "opponent": row["opponent"], "line": row["line"], "americanOdds": row["american_odds"], "finalEdgePercent": 1})

    def explode_save(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("save_playerboard_snapshot should not run when save=False")

    monkeypatch.setattr(builder, "save_playerboard_snapshot", explode_save)

    payload = builder.build_playerboard(season=2026, date_label="2026-06-24", limit=1, save=False, source_mode="propline")

    assert payload["saved"] is None


def test_benchmark_warning_names_slowest_timing_bucket() -> None:
    warning = benchmark_warning(
        {
            "elapsedSeconds": 91,
            "timings": {"loadPropsMs": 5, "unifiedPropCardMs": 500, "hitProfileMs": 10, "totalMs": 91000},
        }
    )

    assert "unifiedPropCardMs" in warning
