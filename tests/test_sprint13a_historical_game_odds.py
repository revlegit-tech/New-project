from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.game_market_grading_service import GameMarketGradingService, profit_1u
from mlb_app.services.historical_game_odds_import_service import (
    LEAKAGE_FORBIDDEN_FEATURE_KEYS,
    HistoricalGameOddsImportService,
    american_implied_probability,
    flatten_game_odds,
    no_vig_probabilities,
    normalize_game,
    stable_game_id,
)


FIXTURE_PAYLOAD = {
    "2021-04-01": [
        {
            "gameView": {
                "startDate": "2021-04-01T17:05:00+00:00",
                "awayTeam": {"fullName": "Toronto Blue Jays", "shortName": "TOR"},
                "homeTeam": {"fullName": "New York Yankees", "shortName": "NYY"},
                "awayTeamScore": 3,
                "homeTeamScore": 2,
                "gameStatusText": "Final",
                "venueName": "Yankee Stadium",
                "gameType": "R",
            },
            "odds": {
                "moneyline": [
                    {
                        "sportsbook": "FanDuel",
                        "openingLine": {"homeOdds": -188, "awayOdds": 155},
                        "currentLine": {"homeOdds": -200, "awayOdds": 168},
                    }
                ],
                "pointspread": [
                    {
                        "sportsbook": "FanDuel",
                        "openingLine": {"homeOdds": 122, "awayOdds": -144, "homeSpread": -1.5, "awaySpread": 1.5},
                        "currentLine": {"homeOdds": 100, "awayOdds": -120, "homeSpread": -1.5, "awaySpread": 1.5},
                    }
                ],
                "totals": [
                    {
                        "sportsbook": "FanDuel",
                        "openingLine": {"overOdds": -106, "underOdds": -114, "total": 8},
                        "currentLine": {"overOdds": -122, "underOdds": 100, "total": 7.5},
                    }
                ],
            },
        }
    ]
}


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
    }
    values.update(overrides)
    return Settings(**values)


def make_repo(tmp_path: Path) -> tuple[Settings, HistoricalGameOddsRepository]:
    settings = make_settings(
        tmp_path,
        db_enabled=True,
        database_url=f"sqlite:///{tmp_path / 'warehouse.sqlite3'}",
    )
    repository = HistoricalGameOddsRepository(WarehouseDatabase.from_settings(settings), settings=settings)
    repository.initialize_schema()
    return settings, repository


def test_importer_parses_small_fixture_and_normalizes_markets() -> None:
    service = HistoricalGameOddsImportService(repository=None)  # type: ignore[arg-type]
    parsed = service.parse_payload(FIXTURE_PAYLOAD)

    assert parsed.games_read == 1
    assert len(parsed.games) == 1
    assert len(parsed.lines) == 6
    assert parsed.games[0]["away_team"] == "TOR"
    assert parsed.games[0]["home_team"] == "NYY"
    assert {row["market"] for row in parsed.lines} == {"moneyline", "run_line", "game_total_runs"}


def test_stable_game_id_generation() -> None:
    first = stable_game_id(
        game_date="2021-04-01",
        away_team="TOR",
        home_team="NYY",
        start_time_utc="2021-04-01T17:05:00Z",
    )
    second = stable_game_id(
        game_date="2021-04-01",
        away_team="TOR",
        home_team="NYY",
        start_time_utc="2021-04-01T17:05:00Z",
    )

    assert first == second
    assert first.startswith("historical_game_")


def test_moneyline_pointspread_and_totals_rows_normalize_correctly() -> None:
    raw_game = FIXTURE_PAYLOAD["2021-04-01"][0]
    game = normalize_game(raw_game, fallback_date="2021-04-01")
    rows = flatten_game_odds(raw_game, game)

    home_ml = next(row for row in rows if row["market"] == "moneyline" and row["side"] == "home")
    away_runline = next(row for row in rows if row["market"] == "run_line" and row["side"] == "away")
    over_total = next(row for row in rows if row["market"] == "game_total_runs" and row["side"] == "over")

    assert home_ml["sportsbook"] == "fanduel"
    assert home_ml["opening_odds"] == -188
    assert home_ml["current_odds"] == -200
    assert away_runline["opening_line"] == 1.5
    assert away_runline["current_odds"] == -120
    assert over_total["opening_line"] == 8.0
    assert over_total["current_line"] == 7.5


def test_american_implied_probability_positive_and_negative_odds() -> None:
    assert american_implied_probability(150) == 0.4
    assert round(american_implied_probability(-200) or 0, 4) == 0.6667


def test_no_vig_probabilities_sum_to_one() -> None:
    probs = no_vig_probabilities(american_implied_probability(-120), american_implied_probability(100))

    assert None not in probs
    assert round(sum(prob or 0 for prob in probs), 6) == 1.0


def test_moneyline_runline_totals_push_and_profit_grading() -> None:
    service = HistoricalGameOddsImportService(repository=None)  # type: ignore[arg-type]
    parsed = service.parse_payload(FIXTURE_PAYLOAD)
    grades = GameMarketGradingService().grade_lines(games=parsed.games, lines=parsed.lines)

    away_moneyline = next(row for row in grades if row["market"] == "moneyline" and row["side"] == "away")
    away_runline = next(row for row in grades if row["market"] == "run_line" and row["side"] == "away")
    under_total = next(row for row in grades if row["market"] == "game_total_runs" and row["side"] == "under")
    push = GameMarketGradingService().grade_line(
        game={"game_id": "g1", "game_date": "2021-04-01", "away_score": 3, "home_score": 2},
        line={"game_id": "g1", "game_date": "2021-04-01", "sportsbook": "book", "market": "game_total_runs", "side": "over", "current_line": 5, "current_odds": -110},
    )

    assert away_moneyline["result"] == "win"
    assert away_runline["result"] == "win"
    assert under_total["result"] == "win"
    assert push is not None
    assert push["result"] == "push"
    assert push["profit_1u"] == 0.0
    assert profit_1u(result="win", odds=150) == 1.5
    assert profit_1u(result="win", odds=-200) == 0.5
    assert profit_1u(result="loss", odds=-200) == -1.0


def test_final_score_fields_do_not_appear_in_pregame_feature_outputs() -> None:
    service = HistoricalGameOddsImportService(repository=None)  # type: ignore[arg-type]
    parsed = service.parse_payload(FIXTURE_PAYLOAD)

    assert parsed.features
    assert not LEAKAGE_FORBIDDEN_FEATURE_KEYS.intersection(parsed.features[0].keys())


def test_repository_can_initialize_sqlite_and_upsert_query_rows(tmp_path: Path) -> None:
    _settings, repository = make_repo(tmp_path)
    service = HistoricalGameOddsImportService(repository)
    parsed = service.parse_payload(FIXTURE_PAYLOAD)
    grades = GameMarketGradingService().grade_lines(games=parsed.games, lines=parsed.lines)

    assert repository.upsert_games(parsed.games) == 1
    assert repository.upsert_lines(parsed.lines) == 6
    assert repository.upsert_features(parsed.features) == 1
    assert repository.upsert_grades(grades) == 6
    assert len(repository.query_lines_by_date("2021-04-01")) == 6
    assert len(repository.query_features_by_date("2021-04-01")) == 1
    assert len(repository.query_grades_by_date("2021-04-01")) == 6


def test_api_status_works_when_warehouse_exists(tmp_path: Path) -> None:
    settings, repository = make_repo(tmp_path)
    parsed = HistoricalGameOddsImportService(repository).parse_payload(FIXTURE_PAYLOAD)
    repository.upsert_games(parsed.games)
    container = AppContainer(settings=settings)
    container.historical_game_odds_repository = repository
    container.data_status_service = DataStatusService(settings=settings, historical_game_odds_repository=repository)
    app = create_app(container=container)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/game-odds/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["reachable"] is True
    assert payload["games"] == 1


def test_api_status_and_data_status_work_when_warehouse_or_dataset_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=False)
    container = AppContainer(settings=settings)
    app = create_app(container=container)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        game_odds_response = client.get("/api/game-odds/status")
        data_status_response = client.get("/api/data/status?season=2026")

    assert game_odds_response.status_code == 200
    assert game_odds_response.json()["enabled"] is False
    assert game_odds_response.json()["sourceFilePresent"] is False
    assert data_status_response.status_code == 200
    assert data_status_response.json()["historical_game_odds"]["source_file_present"] is False


def test_import_endpoint_requires_action_header(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, db_enabled=False)
    app = create_app(container=AppContainer(settings=settings))

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/admin/historical-game-odds/import", json={})

    assert response.status_code == 403
    assert response.json()["code"] == "action_header_required"


def test_optional_csv_exports_are_created_when_enabled(tmp_path: Path) -> None:
    settings, repository = make_repo(tmp_path)
    source_path = settings.data_dir / "external" / "mlb_odds_dataset.json"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(json.dumps(FIXTURE_PAYLOAD), encoding="utf-8")

    result = HistoricalGameOddsImportService(repository, settings=settings).import_file(export_csv=True)

    assert result.status == "success"
    export_dir = settings.data_dir / "warehouse" / "historical_game_odds"
    assert (export_dir / "game_odds_long.csv").exists()
    assert (export_dir / "game_odds_features.csv").exists()
    assert (export_dir / "game_market_grades.csv").exists()
    assert (export_dir / "import_manifest.json").exists()
