from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.contracts.playerboard_schema import (
    PLAYERBOARD_FIELDS,
    PLAYERBOARD_SCHEMA_VERSION,
    normalize_playerboard_row,
    validate_playerboard_header,
)
from mlb_app.contracts.schema_registry import PLAYERBOARD_SCHEMA_REGISTRY
from mlb_app.repositories.playerboard_repository import PlayerboardRepository
from mlb_app.services.playerboard_service import PlayerboardService


class FakeGradingService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, object]:
        return {"ok": True, "state": "graded", "latestFullyGradedDate": "2026-05-04"}


class FakeReadinessService:
    def payload(self, markets: tuple[str, ...], latest_graded_date: str = "") -> dict[str, object]:
        return {"productionEligibleMarkets": list(markets), "latestGradedDate": latest_graded_date}


class FakeProductStateService:
    def payload(self, *, production_eligible_markets: int, grading_ok: bool) -> dict[str, object]:
        return {
            "state": "production" if production_eligible_markets and grading_ok else "research",
            "label": "Ready",
            "message": "Ready",
            "allowedDecisionLabels": ["Add Pick"],
        }


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "data" / "models",
        model_registry_path=tmp_path / "data" / "models" / "model_registry.json",
        current_season=2026,
    )


def _write_playerboard(path: Path, header: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in header})


def _current_row() -> dict[str, object]:
    return {
        "snapshotAt": "2026-05-04T12:00:00Z",
        "season": "2026",
        "date": "2026-05-04",
        "market": "batter_hits_alt",
        "marketDisplay": "Batter Hits Ladder - 4+ Hits",
        "baseMarket": "batter_hits",
        "isAltMarket": "true",
        "player": "Juan Soto",
        "team": "NYY",
        "opponent": "BAL",
        "pitcher": "Example Starter",
        "line": "3.5",
        "americanOdds": "2500",
        "book": "ExampleBook",
        "bookKey": "example",
        "bookCount": "2",
        "books": "[]",
        "finalProbabilityPercent": "8.5",
        "sportsbookImpliedPercent": "3.85",
        "finalEdgePercent": "4.65",
        "confidence": "Low",
        "recommendation": "Alt ladder market",
        "weatherAdjustmentPercent": "0",
        "savantAdjustmentPercent": "0",
        "oddsMovementAdjustmentPercent": "0",
        "missingData": "[]",
        "originalMarket": "batter_hits",
        "rawLabel": "4+ Hits",
        "marketFamily": "batter",
        "hitRates": "[]",
        "recentGames": "[]",
    }


def test_current_playerboard_schema_validates() -> None:
    result = validate_playerboard_header(PLAYERBOARD_FIELDS)

    assert result.ok is True
    assert result.version == PLAYERBOARD_SCHEMA_VERSION
    assert result.order_matches is True
    assert result.missing_required_fields == ()


def test_known_legacy_schema_migrates() -> None:
    legacy_header = [
        "snapshotAt",
        "season",
        "date",
        "market",
        "player",
        "team",
        "opponent",
        "line",
        "americanOdds",
    ]
    rows = [
        {
            "snapshotAt": "2026-05-04T12:00:00Z",
            "season": "2026",
            "date": "2026-05-04",
            "market": "batter_hits_alt",
            "player": "Juan Soto",
            "team": "NYY",
            "opponent": "BAL",
            "line": "3.5",
            "americanOdds": "2500",
        }
    ]

    result = PLAYERBOARD_SCHEMA_REGISTRY.migrate_rows(legacy_header, rows)

    assert result.source_version == "playerboard.legacy.v2"
    assert result.target_version == PLAYERBOARD_SCHEMA_VERSION
    assert result.rows[0]["marketDisplay"] == "Batter Hits Ladder"
    assert result.rows[0]["baseMarket"] == "batter_hits"
    assert result.rows[0]["isAltMarket"] is True


def test_unknown_missing_required_field_fails() -> None:
    header = ["snapshotAt", "season", "date", "player", "team", "opponent", "line", "americanOdds"]

    result = validate_playerboard_header(header)

    assert result.ok is False
    assert result.reason == "missing_required_fields"
    assert "market" in result.missing_required_fields


def test_extra_optional_field_is_preserved_under_extra() -> None:
    header = PLAYERBOARD_FIELDS + ["providerTraceId"]
    result = validate_playerboard_header(header)
    row = _current_row() | {"providerTraceId": "trace-123"}

    normalized = normalize_playerboard_row(row)

    assert result.ok is True
    assert "providerTraceId" in result.extra_fields
    assert normalized["_extra"]["providerTraceId"] == "trace-123"


def test_column_order_drift_does_not_break_stable_field_names() -> None:
    header = list(reversed(PLAYERBOARD_FIELDS))

    result = validate_playerboard_header(header)

    assert result.ok is True
    assert result.order_matches is False
    assert any("column order differs" in warning for warning in result.warnings)


def test_repository_normalizes_app_ready_rows(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = PlayerboardRepository(settings=settings)
    path = repository.path_for_season(2026)
    _write_playerboard(path, PLAYERBOARD_FIELDS, [_current_row()])

    result = repository.read_current_playerboard(season=2026, date_label="2026-05-04", market="batter_hits_alt")

    assert result.validation.ok is True
    assert result.rows[0]["schemaVersion"] == PLAYERBOARD_SCHEMA_VERSION
    assert result.rows[0]["season"] == 2026
    assert result.rows[0]["line"] == 3.5
    assert result.rows[0]["isAltMarket"] is True


def test_playerboard_service_reports_structured_schema_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = PlayerboardRepository(settings=settings)
    path = repository.path_for_season(2026)
    _write_playerboard(
        path,
        ["snapshotAt", "season", "date", "player", "team", "opponent", "line", "americanOdds"],
        [
            {
                "snapshotAt": "2026-05-04T12:00:00Z",
                "season": "2026",
                "date": "2026-05-04",
                "player": "Juan Soto",
                "team": "NYY",
                "opponent": "BAL",
                "line": "3.5",
                "americanOdds": "2500",
            }
        ],
    )
    service = PlayerboardService(
        repository=repository,
        grading_service=FakeGradingService(),  # type: ignore[arg-type]
        readiness_service=FakeReadinessService(),  # type: ignore[arg-type]
        product_state_service=FakeProductStateService(),  # type: ignore[arg-type]
        settings=settings,
    )

    payload = service.health_payload({"season": ["2026"]})

    assert payload["schemaOk"] is False
    assert payload["schemaValidation"]["reason"] == "missing_required_fields"
    assert "market" in payload["schemaValidation"]["missingRequiredFields"]
    assert payload["schemaIssue"]


def test_playerboard_service_returns_normalized_schema_metadata(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = PlayerboardRepository(settings=settings)
    path = repository.path_for_season(2026)
    _write_playerboard(path, PLAYERBOARD_FIELDS, [_current_row()])
    service = PlayerboardService(
        repository=repository,
        grading_service=FakeGradingService(),  # type: ignore[arg-type]
        readiness_service=FakeReadinessService(),  # type: ignore[arg-type]
        product_state_service=FakeProductStateService(),  # type: ignore[arg-type]
        settings=settings,
    )

    payload = service.health_payload({"season": ["2026"], "date": ["2026-05-04"], "market": ["batter_hits_alt"]})

    assert payload["schemaVersion"] == PLAYERBOARD_SCHEMA_VERSION
    assert payload["schemaOk"] is True
    assert payload["rowsLoaded"] == 1
    assert payload["marketsPresent"] == {"batter_hits_alt": 1}



def test_playerboard_health_reports_snapshot_and_recent_game_diagnostics(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = PlayerboardRepository(settings=settings)
    path = repository.path_for_season(2026)

    stale_row = _current_row() | {
        "snapshotAt": "2026-06-23T18:00:00Z",
        "date": "2026-06-23",
        "market": "batter_hits",
        "marketDisplay": "Batter Hits",
        "line": "0.5",
        "recentGames": json.dumps([{"date": "2026-05-06"}]),
    }
    fresh_row = _current_row() | {
        "snapshotAt": "2026-06-23T23:00:00Z",
        "date": "2026-06-23",
        "market": "batter_total_bases",
        "marketDisplay": "Batter Total Bases",
        "line": "1.5",
        "recentGames": json.dumps([{"date": "2026-06-22"}]),
    }

    _write_playerboard(path, PLAYERBOARD_FIELDS, [stale_row, fresh_row])

    service = PlayerboardService(
        repository=repository,
        grading_service=FakeGradingService(),  # type: ignore[arg-type]
        readiness_service=FakeReadinessService(),  # type: ignore[arg-type]
        product_state_service=FakeProductStateService(),  # type: ignore[arg-type]
        settings=settings,
    )

    payload = service.health_payload({"season": ["2026"], "date": ["2026-06-23"]})

    assert payload["rowsLoaded"] == 2
    assert payload["dateRowsInFile"] == 2
    assert payload["snapshotGroupCount"] == 2
    assert payload["latestRecentGameDate"] == "2026-06-22"
    assert payload["rowsWithRecentGames"] == 2
    assert payload["staleRecentGameRows"] == 1
    assert any("Multiple playerboard snapshot groups" in warning for warning in payload["warnings"])
    assert any("stale recentGames" in warning for warning in payload["warnings"])

def test_playerboard_endpoint_returns_empty_saved_dict_without_snapshot(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/playerboard?season=2026&limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == []
    assert payload["saved"] == {}
