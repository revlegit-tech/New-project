from __future__ import annotations

import csv
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from mlb_app.api.app import create_app
from mlb_app.api.models import MarketRegistryResponse, PlayerboardResponse
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.mlb_market_registry_service import MLBMarketRegistryService


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "data" / "models",
        model_registry_path=tmp_path / "data" / "models" / "model_registry.json",
        current_season=2026,
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _registry_by_key(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(row["marketKey"]): row for row in payload["markets"]}  # type: ignore[index]


def test_market_registry_discovers_and_categorizes_all_sources(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_csv(
        settings.data_dir / "odds" / "propline_props_2026-06-23.csv",
        [
            {"date": "2026-06-23", "market": "batter_rbis", "book": "BookA", "player": "A"},
            {"date": "2026-06-23", "market": "batter_2plus_hits", "book": "BookA", "player": "B"},
            {"date": "2026-06-23", "market": "pitcher_outs", "book": "BookB", "player": "P"},
            {"date": "2026-06-23", "market": "moneyline", "book": "BookC", "homeTeam": "NYY"},
            {"date": "2026-06-23", "market": "run_line", "book": "BookC", "homeTeam": "NYY"},
            {"date": "2026-06-23", "market": "game_total_runs", "book": "BookC", "homeTeam": "NYY"},
            {"date": "2026-06-23", "market": "team_total_runs", "book": "BookC", "team": "NYY"},
            {"date": "2026-06-23", "market": "mystery_market", "book": "BookD"},
        ],
    )
    _write_csv(
        settings.data_dir / "warehouse" / "normalized" / "odds" / "actionnetwork_all_markets_2026-06-23.csv",
        [
            {"event_id": "1", "market_group": "first five moneyline", "market": "F5 Moneyline", "book": "BookE"},
            {"event_id": "1", "market_group": "first five total", "market": "F5 Total", "book": "BookE"},
        ],
    )
    _write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [
            {"date": "2026-06-23", "market": "batter_hits", "book": "BookF", "snapshotAt": "2026-06-23T12:00:00Z"},
            {"date": "2026-06-23", "market": "pitcher_strikeouts", "book": "BookF", "snapshotAt": "2026-06-23T12:00:00Z"},
        ],
    )

    payload = MLBMarketRegistryService(settings).payload({"date": ["2026-06-23"], "season": ["2026"]})
    markets = _registry_by_key(payload)

    assert markets["batter_hits"]["category"] == "batter"
    assert markets["batter_rbis"]["category"] == "batter"
    assert markets["batter_2plus_hits"]["hasAltLines"] is True
    assert markets["pitcher_outs"]["category"] == "pitcher"
    assert markets["moneyline"]["category"] == "game"
    assert markets["run_line"]["sideType"] == "spread"
    assert markets["game_total_runs"]["category"] == "game"
    assert markets["team_total_runs"]["category"] == "team"
    assert markets["moneyline_first_five"]["category"] == "first5"
    assert markets["first_five_total_runs"]["category"] == "first5"
    assert markets["mystery_market"]["category"] == "unknown"
    assert markets["mystery_market"]["modelStatus"] == "odds_only"
    assert markets["mystery_market"]["missingModelMarket"] is True
    assert markets["batter_walks"]["hasModel"] is True
    assert markets["batter_walks"]["hasOdds"] is False
    assert markets["batter_walks"]["modelStatus"] == "missing_model"

    coverage = payload["marketCoverage"]  # type: ignore[index]
    assert "batter_rbis" in coverage["marketsDiscoveredFromPropLine"]
    assert "moneyline_first_five" in coverage["marketsDiscoveredFromActionNetwork"]
    assert "batter_hits" in coverage["marketsDiscoveredFromPlayerboard"]
    assert "mystery_market" in coverage["unknownMarketsFound"]
    assert coverage["moneylineRowsLoaded"] == 1
    assert coverage["runLineRowsLoaded"] == 1
    assert coverage["totalsRowsLoaded"] == 1
    assert coverage["teamTotalsRowsLoaded"] == 1
    assert coverage["f5RowsLoaded"] == 2


def test_market_registry_endpoint_exposes_groups_and_research_lock(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_csv(
        settings.data_dir / "odds" / "propline_props_2026-06-23.csv",
        [{"date": "2026-06-23", "market": "batter_hits", "book": "BookA", "player": "A"}],
    )
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/mlb/market-registry?date=2026-06-23&season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"]
    assert payload["marketCoverage"]["marketsShownInDropdown"]
    assert payload["researchLock"] == {
        "action": "Research",
        "readinessLabel": "Experimental",
        "stakeUnits": 0,
        "betActionAllowed": False,
    }


def test_market_registry_response_model_accepts_registry_fields_and_rejects_unexpected() -> None:
    payload = {
        "status": "ok",
        "date": "2026-06-23",
        "season": 2026,
        "markets": [
            {
                "marketKey": "batter_hits",
                "displayName": "Hits",
                "category": "batter",
                "propType": "player",
                "sideType": "over_under",
                "hasOdds": True,
                "hasModel": True,
                "hasAltLines": False,
                "rowCount": 1,
                "quoteCount": 1,
                "availableBooks": ["BookA"],
                "supportedInBoard": True,
                "supportedInReport": True,
                "supportedInModel": True,
                "modelStatus": "modeled",
                "warning": "",
                "warnings": [],
                "sources": ["propline"],
                "missingModelMarket": False,
                "modelUnavailable": False,
                "hidden": False,
                "hiddenReason": "",
                "badges": ["Modeled"],
                "sortableFields": ["rowCount"],
                "marketSupportsModelSort": True,
                "marketSupportsOddsSort": True,
                "marketSupportsEdgeSort": True,
                "marketSupportsLineSort": True,
            }
        ],
        "groups": [{"key": "batter", "label": "Batter Props", "markets": [], "rowCount": 1, "quoteCount": 1}],
        "marketCoverage": {"marketsFound": 1, "marketsShownInDropdown": ["batter_hits"]},
        "coverage": {"marketsFound": 1, "marketsShownInDropdown": ["batter_hits"]},
        "sortableFields": ["edgePercent"],
        "defaultSort": "edgePercent",
        "researchLock": {"action": "Research", "readinessLabel": "Experimental", "stakeUnits": 0, "betActionAllowed": False},
    }

    model = MarketRegistryResponse.model_validate(payload)

    assert model.marketCoverage.marketsShownInDropdown == ["batter_hits"]
    try:
        MarketRegistryResponse.model_validate(payload | {"unexpectedField": True})
    except ValidationError as error:
        assert error.errors()[0]["type"] == "extra_forbidden"
    else:  # pragma: no cover
        raise AssertionError("MarketRegistryResponse accepted an unexpected field")


def test_playerboard_response_model_accepts_registry_fields_and_keeps_strict_response() -> None:
    payload = {
        "status": "ok",
        "schemaVersion": "playerboard.v1",
        "season": 2026,
        "date": "2026-06-23",
        "rows": [],
        "marketRegistry": {"date": "2026-06-23", "markets": [], "groups": []},
        "marketCoverage": {"marketsFound": 0, "marketsShownInDropdown": []},
    }

    model = PlayerboardResponse.model_validate(payload)

    assert model.marketRegistry is not None
    assert model.marketCoverage is not None
    try:
        PlayerboardResponse.model_validate(payload | {"notInContract": True})
    except ValidationError as error:
        assert error.errors()[0]["type"] == "extra_forbidden"
    else:  # pragma: no cover
        raise AssertionError("PlayerboardResponse accepted an unexpected field")


def test_board_routes_validate_market_registry_and_coverage_fields(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_csv(
        settings.data_dir / "playerboard" / "playerboard_2026.csv",
        [{"date": "2026-06-23", "market": "batter_hits", "book": "BookA", "player": "A", "team": "NYY", "opponent": "BAL"}],
    )
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    playerboard_response = client.get("/api/playerboard?date=2026-06-23&season=2026&limit=5")
    edge_response = client.get("/api/edge-board?date=2026-06-23&season=2026&limit=5")

    assert playerboard_response.status_code == 200
    playerboard_payload = playerboard_response.json()
    assert "marketRegistry" in playerboard_payload
    assert "marketCoverage" in playerboard_payload
    assert playerboard_payload["marketRegistry"]["markets"]
    assert playerboard_payload["marketCoverage"]["marketsShownInDropdown"]

    assert edge_response.status_code == 200
    edge_payload = edge_response.json()
    assert "marketRegistry" in edge_payload
    assert "marketCoverage" in edge_payload
    assert edge_payload["marketRegistry"]["groups"]
    assert edge_payload["marketCoverage"]["marketsShownInDropdown"]
