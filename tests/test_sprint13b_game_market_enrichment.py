from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.contracts.playerboard_schema import PLAYERBOARD_FIELDS
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.playerboard_repository import PlayerboardRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.edge_report_service import EdgeReportService
from mlb_app.services.game_market_feature_lookup_service import GameMarketFeatureLookupService
from mlb_app.services.playerboard_read_service import PlayerboardReadService
from mlb_app.services.playerboard_service import PlayerboardService
from mlb_app.services.team_match_utils import normalize_team_alias


FORBIDDEN_PREGAME_KEYS = {
    "home_score",
    "away_score",
    "total_runs",
    "home_win",
    "away_win",
    "game_status",
    "gameStatusText",
    "result",
    "profit_1u",
}


class FakeGradingService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, object]:
        return {"ok": True, "state": "graded", "latestFullyGradedDate": "2026-06-21"}


class FakeReadinessService:
    def payload(self, markets: tuple[str, ...], latest_graded_date: str = "") -> dict[str, object]:
        return {"productionEligibleMarkets": list(markets), "latestGradedDate": latest_graded_date}


class FakeProductStateService:
    def payload(self, *, production_eligible_markets: int, grading_ok: bool) -> dict[str, object]:
        return {"state": "research", "label": "Research", "message": "Research", "allowedDecisionLabels": []}


class FakeModelCardService:
    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        return {"markets": [self.card_for_market("batter_total_bases")]}

    def card_for_market(self, market: str) -> dict[str, Any]:
        return {
            "market": market,
            "readinessLabel": "Research only",
            "productionStatus": "research_only",
            "canShowConfidentPick": False,
            "trainingRows": 50,
            "latestGradedDate": "2026-06-21",
            "calibration": {"status": "uncalibrated"},
            "trustWarnings": [],
        }


class FakePlayerboardService:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def board_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self.payload(query)

    def payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "status": "ok",
            "season": 2026,
            "date": "2026-06-22",
            "top": self.rows,
            "rows": self.rows,
            "cardsBuilt": len(self.rows),
            "propsLoaded": len(self.rows),
            "latestFullyGradedDate": "2026-06-21",
            "dataConfidence": "Good",
            "trust": {},
            "freshness": {"status": "fresh"},
            "productState": {"state": "research"},
        }


class CountingFeatureRepository:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls = 0

    def query_features_by_date(self, date_label: str) -> list[dict[str, Any]]:
        self.calls += 1
        return [row for row in self.rows if row["game_date"] == date_label]


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    values = {
        "root_dir": tmp_path,
        "public_dir": tmp_path / "public",
        "data_dir": data_dir,
        "model_dir": model_dir,
        "model_registry_path": model_dir / "model_registry.json",
        "current_season": 2026,
        "db_path": data_dir / "state.sqlite3",
        "db_enabled": True,
        "database_url": f"sqlite:///{tmp_path / 'warehouse.sqlite3'}",
    }
    values.update(overrides)
    return Settings(**values)


def make_repo(tmp_path: Path) -> tuple[Settings, HistoricalGameOddsRepository]:
    settings = make_settings(tmp_path)
    repository = HistoricalGameOddsRepository(WarehouseDatabase.from_settings(settings), settings=settings)
    repository.initialize_schema()
    return settings, repository


def feature_row(game_id: str = "game-1", *, away_team: str = "BAL", home_team: str = "NYY") -> dict[str, Any]:
    return {
        "game_id": game_id,
        "game_date": "2026-06-22",
        "season": 2026,
        "away_team": away_team,
        "home_team": home_team,
        "venue": "Yankee Stadium",
        "consensus_open_total": 8.0,
        "consensus_current_total": 8.5,
        "total_line_movement": 0.5,
        "home_open_moneyline_consensus": -150,
        "away_open_moneyline_consensus": 130,
        "home_current_moneyline_consensus": -165,
        "away_current_moneyline_consensus": 145,
        "home_no_vig_win_prob_open": 0.58,
        "away_no_vig_win_prob_open": 0.42,
        "home_no_vig_win_prob_current": 0.61,
        "away_no_vig_win_prob_current": 0.39,
        "favorite_team_open": home_team,
        "favorite_team_current": home_team,
        "book_count_moneyline": 4,
        "book_count_total": 3,
        "book_count_runline": 2,
        "market_disagreement_score": 0.1,
        "quality_flags": ["ok"],
    }


def prop_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "snapshotAt": "2026-06-22T12:00:00Z",
        "season": "2026",
        "date": "2026-06-22",
        "market": "batter_total_bases",
        "marketDisplay": "Batter Total Bases",
        "player": "Aaron Judge",
        "team": "NYY",
        "opponent": "BAL",
        "line": "1.5",
        "americanOdds": "-110",
        "book": "ExampleBook",
        "finalProbabilityPercent": "57.5",
        "sportsbookImpliedPercent": "52.4",
        "finalEdgePercent": "5.1",
        "confidence": "Medium",
        "recommendation": "Watch",
        "books": "[]",
        "missingData": "[]",
        "hitRates": "{}",
        "recentGames": "[]",
    }
    row.update(overrides)
    return row


def write_playerboard(settings: Settings, rows: list[dict[str, Any]]) -> None:
    path = settings.data_dir / "playerboard" / "playerboard_2026.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAYERBOARD_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PLAYERBOARD_FIELDS})


def playerboard_service(settings: Settings, lookup: GameMarketFeatureLookupService | None) -> PlayerboardService:
    repository = PlayerboardRepository(settings=settings)
    read_service = PlayerboardReadService(
        repository=repository,
        grading_service=FakeGradingService(),  # type: ignore[arg-type]
        readiness_service=FakeReadinessService(),  # type: ignore[arg-type]
        product_state_service=FakeProductStateService(),  # type: ignore[arg-type]
        game_market_feature_lookup_service=lookup,
        settings=settings,
    )
    return PlayerboardService(
        repository=repository,
        grading_service=FakeGradingService(),  # type: ignore[arg-type]
        readiness_service=FakeReadinessService(),  # type: ignore[arg-type]
        product_state_service=FakeProductStateService(),  # type: ignore[arg-type]
        read_service=read_service,
        game_market_feature_lookup_service=lookup,
        settings=settings,
    )


def test_team_alias_normalization_supports_common_variants() -> None:
    assert normalize_team_alias("AZ") == "ARI"
    assert normalize_team_alias("CWS") == "CHW"
    assert normalize_team_alias("KC") == "KCR"
    assert normalize_team_alias("SD") == "SDP"
    assert normalize_team_alias("SF") == "SFG"
    assert normalize_team_alias("TB") == "TBR"
    assert normalize_team_alias("WAS") == "WSN"


def test_lookup_matches_by_date_team_and_opponent(tmp_path: Path) -> None:
    _settings, repository = make_repo(tmp_path)
    repository.upsert_features([feature_row()])

    feature = GameMarketFeatureLookupService(repository).feature_for_matchup(
        date="2026-06-22",
        team="New York Yankees",
        opponent="Baltimore Orioles",
    )

    assert feature["game_market_enrichment_status"] == "matched"
    assert feature["game_market_team_is_favorite_current"] is True
    assert feature["game_market_team_no_vig_win_prob_current"] == 0.61
    assert not FORBIDDEN_PREGAME_KEYS.intersection(feature)


def test_lookup_returns_noop_on_missing_db() -> None:
    rows = GameMarketFeatureLookupService(None).enrich_rows([prop_row()])

    assert rows[0]["game_market_available"] is False
    assert rows[0]["game_market_enrichment_status"] == "warehouse_unavailable"


def test_lookup_returns_ambiguous_status_for_multiple_same_team_games(tmp_path: Path) -> None:
    _settings, repository = make_repo(tmp_path)
    repository.upsert_features([feature_row("game-1"), feature_row("game-2")])

    rows = GameMarketFeatureLookupService(repository).enrich_rows([prop_row()])

    assert rows[0]["game_market_available"] is False
    assert rows[0]["game_market_enrichment_status"] == "ambiguous_match"


def test_playerboard_rows_gain_game_market_fields_when_matched(tmp_path: Path) -> None:
    settings, repository = make_repo(tmp_path)
    repository.upsert_features([feature_row()])
    write_playerboard(settings, [prop_row()])

    payload = playerboard_service(settings, GameMarketFeatureLookupService(repository, settings=settings)).board_payload(
        {"season": ["2026"], "date": ["2026-06-22"]}
    )

    row = payload["rows"][0]
    assert row["game_market_available"] is True
    assert row["game_market_game_id"] == "game-1"
    assert payload["meta"]["gameMarketEnrichment"]["matchedRows"] == 1
    assert not FORBIDDEN_PREGAME_KEYS.intersection(row)


def test_playerboard_still_works_when_game_market_data_absent(tmp_path: Path) -> None:
    settings, repository = make_repo(tmp_path)
    write_playerboard(settings, [prop_row()])

    payload = playerboard_service(settings, GameMarketFeatureLookupService(repository, settings=settings)).board_payload(
        {"season": ["2026"], "date": ["2026-06-22"]}
    )

    assert payload["rows"][0]["player"] == "Aaron Judge"
    assert payload["rows"][0]["game_market_available"] is False
    assert payload["rows"][0]["game_market_enrichment_status"] == "not_found"


def test_edge_board_rows_gain_game_market_fields_when_matched(tmp_path: Path) -> None:
    settings, repository = make_repo(tmp_path)
    repository.upsert_features([feature_row()])

    payload = EdgeBoardService(
        playerboard_service=FakePlayerboardService([prop_row()]),  # type: ignore[arg-type]
        model_card_service=FakeModelCardService(),  # type: ignore[arg-type]
        game_market_feature_lookup_service=GameMarketFeatureLookupService(repository, settings=settings),
        settings=settings,
    ).payload({"season": ["2026"], "date": ["2026-06-22"]})

    row = payload["rows"][0]
    assert row["game_market_available"] is True
    assert row["game_market_consensus_current_total"] == 8.5
    assert payload["source"]["gameMarketEnrichment"]["matchedRows"] == 1


def test_edge_board_still_works_when_lookup_unavailable() -> None:
    payload = EdgeBoardService(
        playerboard_service=FakePlayerboardService([prop_row()]),  # type: ignore[arg-type]
        model_card_service=FakeModelCardService(),  # type: ignore[arg-type]
    ).payload({"season": ["2026"], "date": ["2026-06-22"]})

    assert payload["rows"][0]["player"] == "Aaron Judge"
    assert payload["rows"][0]["game_market_available"] is False
    assert payload["rows"][0]["game_market_enrichment_status"] == "warehouse_unavailable"


def test_research_report_includes_game_market_context_when_available() -> None:
    row = prop_row(
        game_market_available=True,
        game_market_enrichment_status="matched",
        game_market_consensus_current_total=8.5,
        game_market_total_line_movement=0.5,
        game_market_team_is_favorite_current=True,
        game_market_disagreement_score=0.1,
    )

    payload = EdgeReportService(edge_board_service=FakePlayerboardService([row])).payload({"date": ["2026-06-22"]})  # type: ignore[arg-type]
    card = payload["sections"][0]["cards"][0]

    assert "Game total moved up 0.5 runs." in card["reasons"]
    assert "Team is a current market favorite." in card["reasons"]
    assert card["gameMarketContext"]["status"] == "matched"


def test_research_report_still_works_when_game_market_context_unavailable() -> None:
    payload = EdgeReportService(edge_board_service=FakePlayerboardService([prop_row()])).payload({"date": ["2026-06-22"]})  # type: ignore[arg-type]
    card = payload["sections"][0]["cards"][0]

    assert "No game-market context available." in card["reasons"]
    assert card["gameMarketContext"]["available"] is False


def test_batch_lookup_uses_one_query_per_date() -> None:
    repository = CountingFeatureRepository([feature_row()])
    lookup = GameMarketFeatureLookupService(repository)  # type: ignore[arg-type]

    rows = lookup.enrich_rows([prop_row(player="Aaron Judge"), prop_row(player="Juan Soto")])

    assert repository.calls == 1
    assert [row["game_market_enrichment_status"] for row in rows] == ["matched", "matched"]


def test_data_status_includes_game_market_enrichment_section(tmp_path: Path) -> None:
    settings, repository = make_repo(tmp_path)
    repository.upsert_features([feature_row()])
    lookup = GameMarketFeatureLookupService(repository, settings=settings)
    lookup.enrich_rows([prop_row()])

    payload = DataStatusService(
        settings=settings,
        historical_game_odds_repository=repository,
        game_market_feature_lookup_service=lookup,
    ).payload({"season": ["2026"]})

    section = payload["game_market_enrichment"]
    assert section["enabled"] is True
    assert section["feature_rows"] == 1
    assert section["latest_feature_date"] == "2026-06-22"
    assert section["matched_rows_last_request"] == 1


def test_openapi_builds_with_game_market_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=False, database_url="")
    app = create_app(container=AppContainer(settings=settings))

    schema = app.openapi()

    assert "/api/playerboard" in schema["paths"]
    assert "/api/data/status" in schema["paths"]
