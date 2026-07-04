from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.shadow_model_summary_service import SHADOW_MARKETS, ShadowModelSummaryService


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_shadow_market(settings: Settings, market: str, *, evaluated_rows: int = 250) -> None:
    artifact_dir = settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic" / market
    write_json(
        artifact_dir / "backtest_metrics.json",
        {
            "market": market,
            "modelStage": "shadow",
            "modelKey": "calibrated_logistic",
            "evaluatedRows": evaluated_rows,
            "positiveRows": 101,
            "negativeRows": 149,
            "auc": 0.61,
            "brierScore": 0.22,
            "logLoss": 0.63,
            "validationDates": ["2026-06-23", "2026-06-24"],
            "generatedAt": "2026-07-04T05:47:37+00:00",
            "readinessLabel": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "betActionAllowed": False,
            "warnings": [],
        },
    )
    write_json(
        artifact_dir / "calibration.json",
        {
            "market": market,
            "modelStage": "shadow",
            "modelKey": "calibrated_logistic",
            "sampleCount": evaluated_rows,
            "brierScore": 0.22,
            "logLoss": 0.63,
            "expectedCalibrationError": 0.11,
            "generatedAt": "2026-07-04T05:47:37+00:00",
            "readinessLabel": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "betActionAllowed": False,
        },
    )
    write_json(
        artifact_dir / "shadow_manifest.json",
        {
            "market": market,
            "modelStage": "shadow",
            "modelKey": "calibrated_logistic",
            "backtestStatus": "ready",
            "calibrationStatus": "ready",
            "generatedAt": "2026-07-04T05:47:37+00:00",
            "readinessLabel": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "betActionAllowed": False,
        },
    )


def write_registry(settings: Settings, markets: tuple[str, ...] = SHADOW_MARKETS) -> None:
    registry = {
        market: {
            "production": {
                "status": "production",
                "model_key": "legacy_baseline",
                "artifact": str(settings.data_dir / "models" / "baseline" / market / "model.joblib"),
            },
            "shadow": {
                "status": "shadow",
                "selected_model": "calibrated_logistic",
                "version": "sprint19-20260704T050002Z",
                "model_key": "calibrated_logistic",
                "artifact": str(settings.data_dir / "models" / "artifacts" / "sprint19" / market / "calibrated_logistic" / "model.joblib"),
                "positive_rows": 101,
                "negative_rows": 149,
            },
        }
        for market in markets
    }
    write_json(settings.model_registry_path, registry)


def test_shadow_summary_reports_all_four_sprint19_markets_and_research_lock(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    for market in SHADOW_MARKETS:
        write_shadow_market(settings, market)

    payload = ShadowModelSummaryService(settings).payload()

    assert payload["marketCount"] == 4
    assert payload["readyMarketCount"] == 4
    assert {row["market"] for row in payload["markets"]} == set(SHADOW_MARKETS)
    for row in payload["markets"]:
        assert row["modelStage"] == "shadow"
        assert row["modelKey"] == "calibrated_logistic"
        assert row["version"] == "sprint19-20260704T050002Z"
        assert row["artifactStatus"] == "ready"
        assert row["evaluatedRows"] == 250
        assert row["positiveRows"] == 101
        assert row["negativeRows"] == 149
        assert row["auc"] == 0.61
        assert row["brierScore"] == 0.22
        assert row["logLoss"] == 0.63
        assert row["expectedCalibrationError"] == 0.11
        assert row["validationDates"] == ["2026-06-23", "2026-06-24"]
        assert row["readinessLabel"] == "Experimental"
        assert row["action"] == "Research"
        assert row["stakeUnits"] == 0
        assert row["betActionAllowed"] is False
        assert row["provenance"]["prefersSprint19ShadowArtifacts"] is True
        assert row["provenance"]["fallbackUsed"] is False
        assert any("Sprint 19 shadow" in warning for warning in row["warnings"])


def test_shadow_summary_missing_artifacts_warns_without_fabricating_metrics(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))

    row = ShadowModelSummaryService(settings).payload(market="batter_hits")["markets"][0]

    assert row["artifactStatus"] == "missing"
    assert row["evaluatedRows"] is None
    assert row["auc"] is None
    assert row["brierScore"] is None
    assert row["expectedCalibrationError"] is None
    assert row["readinessLabel"] == "Experimental"
    assert row["action"] == "Research"
    assert row["stakeUnits"] == 0
    assert row["betActionAllowed"] is False
    assert any("not fabricated" in warning for warning in row["warnings"])


def test_shadow_summary_endpoint_and_status_preserve_shadow_count(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    for market in SHADOW_MARKETS:
        write_shadow_market(settings, market)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    summary = client.get("/api/ml-models/shadow-summary")
    status = client.get("/api/ml-models/status")

    assert summary.status_code == 200
    payload = summary.json()
    assert payload["schemaVersion"] == "ml-models.v1"
    assert payload["modelStage"] == "shadow"
    assert payload["modelKey"] == "calibrated_logistic"
    assert payload["marketCount"] == 4
    assert all(row["betActionAllowed"] is False for row in payload["markets"])
    assert status.status_code == 200
    assert status.json()["modelCounts"]["shadow"] == 4
    assert "production" not in status.json()["modelCounts"] or status.json()["modelCounts"]["production"] == 4


def test_shadow_prediction_preview_is_explicitly_research_only(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/ml-models/predictions/preview?market=batter_hits&modelStage=shadow")

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["modelStage"] == "shadow"
    assert preview["modelKey"] == "calibrated_logistic"
    assert preview["previewLabel"] == "Experimental/Shadow"
    assert preview["readinessLabel"] == "Experimental"
    assert preview["action"] == "Research"
    assert preview["stakeUnits"] == 0
    assert preview["betActionAllowed"] is False
    assert preview["available"] is False
