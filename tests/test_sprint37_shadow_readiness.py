from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.shadow_model_readiness_service import ShadowModelReadinessService
from mlb_app.services.shadow_model_summary_service import SHADOW_MARKETS


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_registry(settings: Settings, markets: tuple[str, ...] = SHADOW_MARKETS) -> None:
    registry = {}
    for market in markets:
        registry[market] = {
            "production": {
                "status": "production",
                "model_key": "legacy_baseline",
                "artifact": str(settings.data_dir / "models" / "baseline" / market / "model.joblib"),
                "backtest": {"evaluatedRows": 200, "brierScore": 0.25},
                "metrics": {"logLoss": 0.7},
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
    write_json(settings.model_registry_path, registry)


def write_baseline_metrics(settings: Settings, market: str = "batter_hits") -> None:
    baseline_dir = settings.data_dir / "models" / "baseline" / market
    write_json(
        baseline_dir / "backtest_metrics.json",
        {
            "evaluatedRows": 220,
            "positiveRows": 90,
            "negativeRows": 130,
            "auc": 0.55,
            "brierScore": 0.24,
            "logLoss": 0.69,
            "validationDates": ["2026-06-20"],
            "generatedAt": "2026-07-03T00:00:00+00:00",
        },
    )
    write_json(
        baseline_dir / "calibration.json",
        {
            "sampleCount": 220,
            "expectedCalibrationError": 0.16,
            "brierScore": 0.24,
            "logLoss": 0.69,
        },
    )


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


def test_shadow_readiness_returns_all_four_markets_and_compares_baseline(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    write_baseline_metrics(settings, "batter_hits")
    for market in SHADOW_MARKETS:
        write_shadow_market(settings, market)

    payload = ShadowModelReadinessService(settings).payload()

    assert payload["schemaVersion"] == "shadow-model-readiness.v1"
    assert payload["marketCount"] == 4
    assert payload["blockedMarketCount"] == 4
    assert {row["market"] for row in payload["markets"]} == set(SHADOW_MARKETS)
    hits = next(row for row in payload["markets"] if row["market"] == "batter_hits")
    assert hits["shadow"]["source"] == "sprint19_shadow"
    assert hits["baseline"]["source"] == "legacy_production"
    assert hits["baseline"]["metrics"]["evaluatedRows"] == 200
    assert hits["metricDeltas"]["brierScore"] == -0.03
    assert hits["productionEligible"] is False
    assert "missing_artifact_hash" in hits["blockers"]


def test_shadow_readiness_missing_baseline_warns_without_failing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    write_shadow_market(settings, "batter_hits")
    registry = json.loads(settings.model_registry_path.read_text(encoding="utf-8"))
    registry["batter_hits"].pop("production")
    write_json(settings.model_registry_path, registry)

    row = ShadowModelReadinessService(settings).payload(market="batter_hits")["markets"][0]

    assert row["baseline"]["source"] == "missing"
    assert row["baseline"]["metrics"] == {}
    assert row["productionEligible"] is False
    assert any("No comparable baseline" in warning for warning in row["warnings"])


def test_shadow_readiness_endpoint_preserves_research_locks_and_status_counts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    for market in SHADOW_MARKETS:
        write_shadow_market(settings, market)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    readiness = client.get("/api/ml-models/shadow-readiness")
    status = client.get("/api/ml-models/status")
    summary = client.get("/api/ml-models/shadow-summary")

    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["marketCount"] == 4
    assert payload["promotionCommandPreview"]["enabled"] is False
    assert "/api/admin/ml-models/promote" in payload["promotionCommandPreview"]["message"]
    for row in payload["markets"]:
        assert row["action"] == "Research"
        assert row["readinessLabel"] == "Experimental"
        assert row["stakeUnits"] == 0
        assert row["betActionAllowed"] is False
        assert row["productionEligible"] is False
    assert status.json()["modelCounts"]["shadow"] == 4
    assert summary.json()["marketCount"] == 4
    assert summary.json()["readyMarketCount"] == 4


def test_shadow_readiness_does_not_call_promote(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    write_shadow_market(settings, "batter_hits")
    container = AppContainer(settings=settings)

    def fail_if_called(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("promote path must not be called by readiness")

    container.model_registry_service.transition_model_status = fail_if_called  # type: ignore[method-assign]
    client = TestClient(create_app(container=container), client=("127.0.0.1", 50000))

    response = client.get("/api/ml-models/shadow-readiness?market=batter_hits")

    assert response.status_code == 200
    assert response.json()["markets"][0]["productionEligible"] is False
