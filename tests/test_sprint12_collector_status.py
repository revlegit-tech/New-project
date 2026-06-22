from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.collector_manifest_service import CollectorManifestService
from mlb_app.services.data_status_service import DataStatusService
from mlb_app.services.edge_board_snapshot_service import EdgeBoardSnapshotService


NOW = datetime(2026, 6, 22, 15, 0, tzinfo=timezone.utc)


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=model_dir / "model_registry.json",
        current_season=2026,
        db_path=data_dir / "state.sqlite3",
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["date", "market"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        import csv

        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))


def seed_complete_data(settings: Settings, *, include_edge_board: bool = True) -> None:
    data = settings.data_dir
    write_csv(data / "odds" / "propline_props_2026-06-22.csv", [
        {"date": "2026-06-22", "market": "batter_hits", "player": "A"},
        {"date": "2026-06-22", "market": "batter_total_bases", "player": "B"},
    ])
    write_csv(data / "warehouse" / "odds_snapshots" / "propline_props_2026-06-22_150000.csv", [
        {"date": "2026-06-22", "market": "batter_hits"},
    ])
    write_json(data / "warehouse" / "raw" / "boxscores_2026-06-22.json", {"games": []})
    write_json(data / "warehouse" / "summaries" / "daily_summary_2026-06-22.json", {"propCount": 2})
    write_json(data / "warehouse" / "logs" / "season_collector_manual_2026-06-22_run.json", {"ok": True})
    write_csv(data / "playerboard" / "playerboard_2026.csv", [
        {"date": "2026-06-22", "market": "batter_hits", "player": "A"},
        {"date": "2026-06-22", "market": "batter_hits", "player": "B"},
    ])
    if include_edge_board:
        write_csv(data / "edge_board" / "edge_board_2026-06-22.csv", [
            {"date": "2026-06-22", "market": "batter_hits", "player": "A"},
        ])
    write_json(data / "cloud" / "summaries" / "latest_collector_run.json", {"success": True})
    write_json(data / "cache" / "odds_movement" / "status_2026.json", {"success": True})
    write_csv(data / "cache" / "odds_movement" / "prop_movement_2026.csv", [
        {"date": "2026-06-22", "market": "batter_hits"},
    ])
    write_csv(data / "cache" / "odds_movement" / "prop_snapshots_2026.csv", [
        {"date": "2026-06-22", "market": "batter_hits"},
    ])


def test_collector_manifest_writer_preserves_required_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_complete_data(settings)
    summary = {
        "runId": "run-123",
        "date": "2026-06-22",
        "runType": "manual",
        "startedAt": "2026-06-22T14:59:00+00:00",
        "finishedAt": "2026-06-22T15:00:00+00:00",
        "success": True,
        "result": {
            "dataHub": {"propCount": 2, "mlbGames": 7},
            "logs": {"batterRowsUpserted": 18},
        },
        "warnings": ["minor warning"],
        "traceback": "x" * 5000,
    }

    result = CollectorManifestService(settings=settings, now_provider=lambda: NOW).write_manifest(
        summary,
        requested_markets=["batter_hits", "batter_total_bases"],
    )

    assert result.manifest_path.exists()
    assert result.latest_path.exists()
    assert result.manifest["run_id"] == "run-123"
    assert result.manifest["requested_markets"] == ["batter_hits", "batter_total_bases"]
    assert result.manifest["source_counts"]["propCount"] == 2
    assert result.manifest["market_counts"]["batter_hits"] == 2
    assert result.manifest["playerboard_rows"] == 2
    assert len(result.manifest["traceback_tail"]) == 4000
    assert "traceback" not in result.manifest
    assert not result.manifest["artifact_critical_files_missing"]


def test_latest_manifest_falls_back_to_newest_manifest_file(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    manifest_dir = settings.data_dir / "health" / "collector_manifests"
    manifest_dir.mkdir(parents=True)
    older = manifest_dir / "collector_manifest_2026-06-21_old.json"
    newer = manifest_dir / "collector_manifest_2026-06-22_new.json"
    older.write_text(json.dumps({"run_id": "old", "date": "2026-06-21"}), encoding="utf-8")
    newer.write_text(json.dumps({"run_id": "new", "date": "2026-06-22"}), encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    latest = CollectorManifestService(settings=settings).load_latest_manifest()

    assert latest is not None
    assert latest["run_id"] == "new"
    assert latest["date"] == "2026-06-22"


def test_data_status_service_reports_fresh_sources_and_counts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_complete_data(settings)
    CollectorManifestService(settings=settings, now_provider=lambda: NOW).write_manifest(
        {"runId": "run-123", "date": "2026-06-22", "runType": "manual", "success": True},
        requested_markets=["batter_hits"],
    )

    payload = DataStatusService(settings=settings, now_provider=lambda: NOW).payload({"season": ["2026"]})

    assert payload["status"] == "fresh"
    assert payload["data_health_score"] == 100
    assert payload["source_freshness"]["playerboard"]["row_count"] == 2
    assert payload["source_freshness"]["playerboard"]["market_counts"] == {"batter_hits": 2}
    assert payload["missing_files"] == []
    assert payload["latest_collector_manifest"]["run_id"] == "run-123"


def test_data_status_service_handles_missing_folders(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    payload = DataStatusService(settings=settings, now_provider=lambda: NOW).payload({"season": ["2026"]})

    assert payload["status"] == "missing"
    assert payload["data_health_score"] < 100
    assert payload["source_freshness"]["odds"]["status"] == "missing"
    assert "data/playerboard/playerboard_2026.csv" in payload["missing_files"]
    assert payload["latest_collector_manifest"] is None


def test_data_status_reports_missing_noncritical_edge_board(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_complete_data(settings, include_edge_board=False)
    CollectorManifestService(settings=settings, now_provider=lambda: NOW).write_manifest(
        {"runId": "run-123", "date": "2026-06-22", "runType": "manual", "success": True},
        requested_markets=["batter_hits"],
    )

    payload = DataStatusService(settings=settings, now_provider=lambda: NOW).payload({"season": ["2026"]})

    assert payload["status"] == "warning"
    assert payload["missing_files"] == []
    assert payload["source_freshness"]["edge_board"]["status"] == "missing"
    assert payload["data_health_score"] == 96


def test_edge_board_snapshot_writer_and_status_detection(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_complete_data(settings, include_edge_board=False)

    class FakeEdgeBoardService:
        def payload(self, query: dict[str, list[str]]) -> dict[str, object]:
            return {
                "status": "ok",
                "date": query["date"][0],
                "season": int(query["season"][0]),
                "rows": [
                    {"date": "2026-06-22", "market": "batter_hits", "player": "A", "modelCard": {"nested": True}},
                    {"date": "2026-06-22", "market": "batter_hits", "player": "B"},
                ],
                "rowCount": 2,
            }

    result = EdgeBoardSnapshotService(settings=settings, edge_board_service=FakeEdgeBoardService()).write_snapshot(
        date_label="2026-06-22",
        season=2026,
    )
    os.utime(result.json_path, (NOW.timestamp(), NOW.timestamp()))
    assert result.csv_path is not None
    os.utime(result.csv_path, (NOW.timestamp(), NOW.timestamp()))

    payload = DataStatusService(settings=settings, now_provider=lambda: NOW).payload({"season": ["2026"]})

    assert result.json_path.exists()
    assert result.csv_path.exists()
    assert result.row_count == 2
    assert payload["source_freshness"]["edge_board"]["status"] == "fresh"
    assert payload["source_freshness"]["edge_board"]["latest_file"] in {
        "data/edge_board/edge_board_2026-06-22.json",
        "data/edge_board/edge_board_2026-06-22.csv",
    }
    assert payload["source_freshness"]["edge_board"]["row_count"] == 2
    assert payload["source_freshness"]["edge_board"]["market_counts"] == {"batter_hits": 2}


def test_data_status_endpoint_uses_strict_response_shape(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_complete_data(settings)
    CollectorManifestService(settings=settings, now_provider=lambda: NOW).write_manifest(
        {"runId": "run-123", "date": "2026-06-22", "runType": "manual", "success": True},
        requested_markets=["batter_hits"],
    )
    container = AppContainer(settings=settings)
    container.data_status_service = DataStatusService(settings=settings, now_provider=lambda: NOW)
    app = create_app(container=container)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/data/status?season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "schemaVersion",
        "status",
        "current_date",
        "generated_at",
        "latest_collector_manifest",
        "source_freshness",
        "expected_files",
        "missing_files",
        "warnings",
        "data_health_score",
    }
    assert payload["schemaVersion"] == "data-status.v1"
    assert payload["status"] == "fresh"
    assert "traceback" not in payload["latest_collector_manifest"]
