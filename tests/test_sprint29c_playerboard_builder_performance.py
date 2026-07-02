from __future__ import annotations

import csv

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


def test_builder_corrects_roster_attribution_before_source_rows(monkeypatch) -> None:
    props = [
        {"date": "2026-07-01", "market": "batter_hits", "player": "Bobby Witt", "team": "TBR", "opponent": "KCR", "line": "0.5", "americanOdds": "-110"},
        {"date": "2026-07-01", "market": "batter_hits", "player": "Bobby Witt Jr.", "team": "TBR", "opponent": "KCR", "line": "0.5", "americanOdds": "-105"},
        {"date": "2026-07-01", "market": "batter_hits", "player": "Trea Turner", "team": "PIT", "opponent": "PHI", "line": "0.5", "americanOdds": "-115"},
        {"date": "2026-07-01", "market": "batter_hits", "player": "Jose Altuve", "team": "MIN", "opponent": "HOU", "line": "0.5", "americanOdds": "-120"},
        {"date": "2026-07-01", "market": "batter_hits", "player": "Christian Yelich", "team": "CIN", "opponent": "MIL", "line": "0.5", "americanOdds": "+100"},
        {"date": "2026-07-01", "market": "pitcher_strikeouts_alt", "player": "3+ Strikeouts", "team": "MIL", "opponent": "CIN", "line": "2.5", "americanOdds": "+140"},
    ]
    monkeypatch.setattr(builder, "load_saved_props", lambda *args, **kwargs: props)
    monkeypatch.setattr(
        "mlb_app.domain.unified_prop_card.unified_prop_card",
        lambda row: {
            "player": row["player"],
            "market": row["market"],
            "team": row["team"],
            "opponent": row["opponent"],
            "line": row["line"],
            "americanOdds": row["american_odds"],
            "finalEdgePercent": 1,
        },
    )

    payload = builder.build_playerboard(season=2026, date_label="2026-07-01", limit=10, save=False, source_mode="propline")
    rows = {row["player"]: row for row in payload["top"]}

    assert rows["Bobby Witt"]["team"] == "KANSAS CITY ROYALS"
    assert rows["Bobby Witt"]["opponent"] == "TAMPA BAY RAYS"
    assert rows["Bobby Witt Jr."]["team"] == "KANSAS CITY ROYALS"
    assert rows["Trea Turner"]["team"] == "PHILADELPHIA PHILLIES"
    assert rows["Jose Altuve"]["team"] == "HOUSTON ASTROS"
    assert rows["Christian Yelich"]["team"] == "MILWAUKEE BREWERS"
    for player in ("Bobby Witt", "Bobby Witt Jr.", "Trea Turner", "Jose Altuve", "Christian Yelich"):
        assert rows[player]["attributionStatus"] == "corrected"
        assert rows[player]["attributionConfidence"] == "high"
        assert rows[player]["attributionCorrectionApplied"] is True
        assert rows[player]["playerTeamEvidenceStatus"] == "roster_match"
        assert rows[player]["contextBlockedByAttribution"] is False

    invalid = rows["3+ Strikeouts"]
    assert invalid["attributionStatus"] == "invalid_player_label"
    assert invalid["contextBlockedByAttribution"] is True


def test_builder_uses_slate_roster_index_for_mixed_two_team_board(monkeypatch) -> None:
    props = [
        {"date": "2026-07-01", "market": "batter_hits", "player": "Camden Vale", "team": "TBR", "opponent": "KCR", "line": "0.5", "americanOdds": "-110"},
        {"date": "2026-07-01", "market": "batter_hits", "player": "River Stone", "team": "TBR", "opponent": "KCR", "line": "0.5", "americanOdds": "-105"},
    ]
    monkeypatch.setattr(builder, "load_saved_props", lambda *args, **kwargs: props)

    def fake_read_csv_rows(path):
        if path.name == "player_index_2026.csv":
            return [
                {"player": "Camden Vale", "team": "KCR"},
                {"player": "River Stone", "team": "TBR"},
            ]
        return []

    monkeypatch.setattr(builder, "read_csv_rows", fake_read_csv_rows)
    monkeypatch.setattr(
        "mlb_app.domain.unified_prop_card.unified_prop_card",
        lambda row: {
            "player": row["player"],
            "market": row["market"],
            "team": row["team"],
            "opponent": row["opponent"],
            "line": row["line"],
            "americanOdds": row["american_odds"],
            "finalEdgePercent": 1,
        },
    )

    payload = builder.build_playerboard(season=2026, date_label="2026-07-01", limit=10, save=False, source_mode="propline")
    rows = {row["player"]: row for row in payload["top"]}

    assert rows["Camden Vale"]["team"] == "KANSAS CITY ROYALS"
    assert rows["Camden Vale"]["opponent"] == "TAMPA BAY RAYS"
    assert rows["Camden Vale"]["attributionStatus"] == "corrected"
    assert rows["River Stone"]["team"] == "TAMPA BAY RAYS"
    assert rows["River Stone"]["opponent"] == "KANSAS CITY ROYALS"
    assert rows["River Stone"]["attributionStatus"] == "verified"
    assert payload["attribution"]["rosterResolverRowsChecked"] == 2
    assert payload["attribution"]["rosterResolverRowsMatchedOneSide"] == 2
    assert payload["attribution"]["rosterResolverRowsCorrected"] == 1


def test_builder_uses_cached_evidence_when_live_rows_have_full_team_names(monkeypatch) -> None:
    props = [
        {
            "date": "2026-07-02",
            "market": "batter_hits",
            "player": "Shohei Ohtani",
            "team": "SAN DIEGO PADRES",
            "opponent": "LOS ANGELES DODGERS",
            "line": "0.5",
            "americanOdds": "-110",
        },
        {
            "date": "2026-07-02",
            "market": "batter_hits",
            "player": "Michael Harris",
            "team": "ST. LOUIS CARDINALS",
            "opponent": "ATLANTA BRAVES",
            "line": "0.5",
            "americanOdds": "-105",
        },
    ]
    monkeypatch.setattr(builder, "load_saved_props", lambda *args, **kwargs: props)

    def fake_read_csv_rows(path):
        if path.name == "player_index_2026.csv":
            return [
                {"player": "Shohei Ohtani", "team": "LAD"},
                {"player": "Michael Harris II", "team": "ATL"},
            ]
        return []

    monkeypatch.setattr(builder, "read_csv_rows", fake_read_csv_rows)
    monkeypatch.setattr(
        "mlb_app.domain.unified_prop_card.unified_prop_card",
        lambda row: {
            "player": row["player"],
            "market": row["market"],
            "team": row["team"],
            "opponent": row["opponent"],
            "line": row["line"],
            "americanOdds": row["american_odds"],
            "finalEdgePercent": 1,
        },
    )

    payload = builder.build_playerboard(season=2026, date_label="2026-07-02", limit=10, save=False, source_mode="propline")
    rows = {row["player"]: row for row in payload["top"]}

    assert rows["Shohei Ohtani"]["team"] == "LOS ANGELES DODGERS"
    assert rows["Shohei Ohtani"]["opponent"] == "SAN DIEGO PADRES"
    assert rows["Shohei Ohtani"]["attributionStatus"] == "corrected"
    assert rows["Shohei Ohtani"]["attributionConfidence"] == "high"
    assert rows["Michael Harris"]["team"] == "ATLANTA BRAVES"
    assert rows["Michael Harris"]["opponent"] == "ST. LOUIS CARDINALS"
    assert rows["Michael Harris"]["attributionStatus"] == "corrected"
    assert rows["Michael Harris"]["attributionConfidence"] == "high"
    assert payload["attribution"]["rosterIndexPlayersLoaded"] == 2
    assert payload["attribution"]["rosterIndexTeamsLoaded"] == 2
    assert payload["attribution"]["rosterIndexSourceCounts"]["player_index"] == 2
    assert payload["attribution"]["rosterEvidenceAvailableRows"] == 2
    assert payload["attribution"]["rosterEvidenceUnavailableRows"] == 0
    assert payload["attribution"]["sampleKnownTeamMatches"]
    assert payload["attribution"]["sampleRosterCorrections"]


def test_save_playerboard_snapshot_persists_corrected_attribution(monkeypatch, tmp_path) -> None:
    class FakeBoardSnapshotRepository:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def replace_active_snapshot(self, **kwargs):
            self.rows = kwargs["rows"]
            return type("Snapshot", (), {"id": "snapshot-1"})()

    import mlb_app.repositories.board_snapshot_repository as snapshot_module

    monkeypatch.setattr(builder, "PLAYERBOARD_DIR", tmp_path / "playerboard")
    monkeypatch.setattr(builder, "canonical_prop_files", lambda date_label: [])
    monkeypatch.setattr(snapshot_module, "BoardSnapshotRepository", FakeBoardSnapshotRepository)

    builder.save_playerboard_snapshot(
        2026,
        "2026-07-01",
        [{"date": "2026-07-01", "market": "batter_hits", "player": "Bobby Witt", "team": "TBR", "opponent": "KCR", "line": "0.5", "americanOdds": "-110"}],
        replace_date=True,
    )

    path = tmp_path / "playerboard" / "playerboard_2026.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["player"] == "Bobby Witt"
    assert row["team"] == "KANSAS CITY ROYALS"
    assert row["opponent"] == "TAMPA BAY RAYS"
    assert row["sourceTeam"] == "TBR"
    assert row["sourceOpponent"] == "KCR"
    assert row["attributionStatus"] == "corrected"
    assert row["attributionConfidence"] == "high"
    assert row["attributionCorrectionApplied"] == "True"
    assert row["playerTeamEvidenceStatus"] == "roster_match"


def test_benchmark_warning_names_slowest_timing_bucket() -> None:
    warning = benchmark_warning(
        {
            "elapsedSeconds": 91,
            "timings": {"loadPropsMs": 5, "unifiedPropCardMs": 500, "hitProfileMs": 10, "totalMs": 91000},
        }
    )

    assert "unifiedPropCardMs" in warning
