from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.collector_verification_service import CollectorVerificationService
from mlb_app.services.data_source_capability_service import DataSourceCapabilityService
from mlb_app.services.game_market_artifact_service import GameMarketArtifactService


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    data_dir = tmp_path / "data"
    return replace(settings, data_dir=data_dir, db_path=data_dir / "mlb_app_state.sqlite3", current_season=2026)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def fixture_rows() -> list[dict[str, Any]]:
    return [
        {"date": "2026-06-24", "season": 2026, "game_id": "game-1", "home_team": "NYY", "away_team": "BAL", "team": "NYY", "opponent": "BAL", "market": "moneyline", "american_odds": "-130", "source": "fixture"},
        {"date": "2026-06-24", "season": 2026, "game_id": "game-1", "home_team": "NYY", "away_team": "BAL", "team": "BAL", "opponent": "NYY", "market": "moneyline", "american_odds": "110", "source": "fixture"},
        {"date": "2026-06-24", "season": 2026, "game_id": "game-1", "home_team": "NYY", "away_team": "BAL", "market": "game_total", "line": "8.5", "source": "fixture"},
        {"date": "2026-06-24", "season": 2026, "game_id": "game-1", "home_team": "NYY", "away_team": "BAL", "team": "NYY", "opponent": "BAL", "market": "team_total", "line": "4.5", "source": "fixture"},
    ]


def test_normalized_game_market_artifact_can_be_built_from_fixture_rows(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    result = GameMarketArtifactService(settings).build_from_rows(
        fixture_rows(),
        date_label="2026-06-24",
        season=2026,
        source="fixture",
        snapshot_at="2026-06-24T16:00:00+00:00",
    )

    path = settings.data_dir / "warehouse" / "normalized" / "game_markets" / "game_markets_2026-06-24.csv"
    rows = read_rows(path)

    assert result["rows"] == 4
    assert path.is_file()
    assert {"date", "season", "game_id", "game_pk", "market_type", "current_moneyline", "current_total", "team_total", "quality_flags"} <= set(rows[0])
    assert {row["market_type"] for row in rows} >= {"moneyline", "game_total", "team_total"}


def test_missing_provider_data_returns_clean_missing_status(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    payload = GameMarketArtifactService(settings).status(date_label="2026-06-24")

    assert payload["status"] == "missing"
    assert payload["available"] is False
    assert payload["rows"] == 0


def test_capabilities_and_collector_check_report_game_markets_available(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    GameMarketArtifactService(settings).build_from_rows(fixture_rows(), date_label="2026-06-24", season=2026)

    capabilities = DataSourceCapabilityService(settings).payload(date_label="2026-06-24", season=2026)
    collector = CollectorVerificationService(settings=settings).payload(date_label="2026-06-24", season=2026)

    assert capabilities["sources"]["gameMarkets"]["available"] is True
    assert capabilities["featureGroups"]["gameMarkets"]["criticalForBoard"] is False
    assert collector["checks"]["gameMarkets"]["ok"] is True
    assert collector["counts"]["gameMarketRows"] == 4
