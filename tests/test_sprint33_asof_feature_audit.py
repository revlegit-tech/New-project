from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.asof_feature_audit_service import AsofFeatureAuditService


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    data_dir = tmp_path / "data"
    return replace(settings, data_dir=data_dir, db_path=data_dir / "mlb_app_state.sqlite3", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ["date"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_asof_audit_detects_blocked_label_fields(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-24.csv",
        [{"date": "2026-06-24", "player": "A", "market": "batter_hits", "actual_value": "2", "result": "win"}],
    )

    payload = AsofFeatureAuditService(settings).payload(date_label="2026-06-24", season=2026)

    assert payload["pregameSafe"] is False
    assert payload["labelsSeparated"] is False
    assert set(payload["blockedFieldsFound"]) == {"actual_value", "result"}


def test_asof_audit_passes_clean_pregame_feature_matrix_fixture(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "features" / "prop_features_2026-06-24.csv",
        [{"date": "2026-06-24", "player": "A", "market": "batter_hits", "source_snapshot_at": "2026-06-24T16:00:00+00:00"}],
    )

    payload = AsofFeatureAuditService(settings).payload(date_label="2026-06-24", season=2026)

    assert payload["schemaVersion"] == "asof-feature-audit.v1"
    assert payload["pregameSafe"] is True
    assert payload["labelsSeparated"] is True
    assert payload["blockedFieldsFound"] == []
    assert payload["externalApiCallsMade"] is False
    assert payload["modelTrainingTriggered"] is False


def test_asof_endpoint_is_read_only_and_reports_no_training_or_external_calls(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("as-of audit must not collect data or train models")

    monkeypatch.setattr("mlb_app.integrations.statsapi.warehouse_sync.sync_date", forbidden)
    monkeypatch.setattr("mlb_app.services.model_training_service.ModelTrainingService.train_market", forbidden)
    settings = make_settings(tmp_path)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/runtime/asof-feature-audit?date=today&season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "asof-feature-audit.v1"
    assert payload["externalApiCallsMade"] is False
    assert payload["modelTrainingTriggered"] is False
