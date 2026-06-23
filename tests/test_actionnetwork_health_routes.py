from __future__ import annotations

import csv
import json
from pathlib import Path

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        db_path=data_dir / "state.sqlite3",
        current_season=2026,
    )


def client_for(settings: Settings) -> TestClient:
    return TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))


def test_actionnetwork_trust_route_returns_safe_missing_payload(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = client_for(settings)

    response = client.get("/api/actionnetwork/trust?date=2026-06-23")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["snapshot"]["snapshotFreshness"] == "missing"
    assert payload["labels"]["trainableEligibility"] == "not_trainable"
    text = json.dumps(payload)
    assert str(tmp_path) not in text
    assert "C:\\Users\\" not in text


def test_actionnetwork_trust_route_reports_snapshot_and_event_confirmed_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    snapshot_dir = settings.data_dir / "warehouse" / "normalized" / "odds"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "actionnetwork_all_markets_2026-06-23.csv").write_text("event_id,player\n1,Aaron Judge\n", encoding="utf-8")
    (snapshot_dir / "actionnetwork_all_markets_2026-06-23_120000.csv").write_text("event_id,player\n1,Aaron Judge\n", encoding="utf-8")
    raw_dir = settings.data_dir / "warehouse" / "raw" / "actionnetwork" / "pages" / "snapshots" / "2026-06-23" / "120000"
    raw_dir.mkdir(parents=True)
    (raw_dir / "event.html").write_text("<html></html>", encoding="utf-8")
    label_dir = settings.data_dir / "warehouse" / "normalized" / "actionnetwork"
    label_dir.mkdir(parents=True)
    with (label_dir / "actionnetwork_event_confirmed_labels_2026-06-23.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "collection_mode",
                "bridge_status",
                "validation_status",
                "label_result",
                "exclude_from_ml",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "collection_mode": "live_forward",
                "bridge_status": "confirmed",
                "validation_status": "valid_labeled_event_confirmed",
                "label_result": "win",
                "exclude_from_ml": "0",
            }
        )
    client = client_for(settings)

    payload = client.get("/api/actionnetwork/trust?date=2026-06-23").json()

    assert payload["status"] == "fresh"
    assert payload["snapshot"]["timestampedCsvCount"] == 1
    assert payload["labels"]["eventConfirmed"] == 1
    assert payload["labels"]["trainableRows"] == 1
