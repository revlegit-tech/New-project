from __future__ import annotations

import csv
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
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
