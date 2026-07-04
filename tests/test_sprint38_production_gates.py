from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.model_production_gate_service import MANUAL_GOVERNANCE_BLOCKER, ModelProductionGateService
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.shadow_model_summary_service import SHADOW_MARKETS


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_shadow_market(settings: Settings, market: str, *, fallback_used: bool = False) -> None:
    artifact_dir = settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic" / market
    write_json(
        artifact_dir / "backtest_metrics.json",
        {
            "market": market,
            "modelStage": "shadow",
            "modelKey": "calibrated_logistic",
            "evaluatedRows": 1200,
            "positiveRows": 180,
            "negativeRows": 1020,
            "brierScore": 0.21,
            "logLoss": 0.62,
            "validationDates": ["2026-06-23"],
            "generatedAt": "2026-07-04T05:47:37+00:00",
        },
    )
    write_json(
        artifact_dir / "calibration.json",
        {
            "market": market,
            "modelStage": "shadow",
            "modelKey": "calibrated_logistic",
            "sampleCount": 1200,
            "expectedCalibrationError": 0.08,
            "brierScore": 0.21,
            "logLoss": 0.62,
            "generatedAt": "2026-07-04T05:47:37+00:00",
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
            "sourcePath": "data/warehouse/ml_labels",
            "provenance": {"fallbackUsed": fallback_used},
        },
    )


def write_registry(settings: Settings, markets: tuple[str, ...] = SHADOW_MARKETS) -> None:
    registry: dict[str, Any] = {}
    for market in markets:
        model_path = settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic" / market / "model.joblib"
        feature_path = model_path.with_name("feature_schema.json")
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_bytes(b"model")
        write_json(feature_path, {"feature_names": ["feature_line"]})
        registry[market] = {
            "candidate": {
                "status": "candidate",
                "model_key": "random_forest",
                "source": "legacy_candidate",
                "metrics": {"evaluatedRows": 100, "brierScore": 0.3},
            },
            "shadow": {
                "status": "shadow",
                "selected_model": "calibrated_logistic",
                "version": "sprint19-20260704T050002Z",
                "model_key": "calibrated_logistic",
                "artifact": model_path.relative_to(settings.root_dir).as_posix(),
                "features": feature_path.relative_to(settings.root_dir).as_posix(),
                "artifact_sha256": "a" * 64,
                "features_sha256": "b" * 64,
                "positive_rows": 180,
                "negative_rows": 1020,
                "training_rows": 1200,
                "calibrated": True,
            },
        }
    write_json(settings.model_registry_path, registry)


def test_shadow_readiness_includes_gate_matrix_for_all_markets(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    for market in SHADOW_MARKETS:
        write_shadow_market(settings, market)

    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))
    payload = client.get("/api/ml-models/shadow-readiness").json()

    assert payload["marketCount"] == 4
    assert payload["readyMarketCount"] == 0
    assert payload["blockedMarketCount"] == 4
    for row in payload["markets"]:
        assert row["gateChecks"]
        assert row["gateSummary"]["manualGovernanceRequired"] is True
        assert MANUAL_GOVERNANCE_BLOCKER in row["hardBlockers"]
        assert MANUAL_GOVERNANCE_BLOCKER in row["blockers"]
        assert row["productionEligible"] is False
        assert row["productionGateStatus"] != "pass"
        assert row["action"] == "Research"
        assert row["readinessLabel"] == "Experimental"
        assert row["stakeUnits"] == 0
        assert row["betActionAllowed"] is False


def test_production_gates_endpoint_is_read_only_and_blocks_manual_governance(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    write_shadow_market(settings, "batter_hits")
    container = AppContainer(settings=settings)

    def fail_if_called(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("promotion path must not be called by production gates endpoint")

    container.model_registry_service.transition_model_status = fail_if_called  # type: ignore[method-assign]
    client = TestClient(create_app(container=container), client=("127.0.0.1", 50000))

    response = client.get("/api/ml-models/production-gates?market=batter_hits")

    assert response.status_code == 200
    payload = response.json()
    assert payload["marketCount"] == 1
    assert payload["readyMarketCount"] == 0
    assert payload["blockedMarketCount"] == 1
    assert payload["markets"][0]["productionEligible"] is False
    assert MANUAL_GOVERNANCE_BLOCKER in payload["markets"][0]["hardBlockers"]


def test_missing_artifacts_and_fallback_used_are_hard_blockers(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    write_shadow_market(settings, "batter_hits", fallback_used=True)
    (settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic" / "batter_hits" / "backtest_metrics.json").unlink()

    row = ModelProductionGateService(settings).payload(market="batter_hits", registry=json.loads(settings.model_registry_path.read_text(encoding="utf-8")))["markets"][0]

    assert "backtest_exists" in row["hardBlockers"]
    assert "missing_shadow_backtest" in row["hardBlockers"]
    assert "fallback_used_false" in row["hardBlockers"]
    assert MANUAL_GOVERNANCE_BLOCKER in row["hardBlockers"]


def test_promotion_preflight_denies_sprint19_shadow_without_registry_mutation(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    before = settings.model_registry_path.read_text(encoding="utf-8")

    result = ModelRegistryService(settings).transition_model_status(
        "batter_hits",
        "production",
        source_status="shadow",
        model_key="calibrated_logistic",
    )

    after = settings.model_registry_path.read_text(encoding="utf-8")
    assert result["status"] == "rejected"
    assert MANUAL_GOVERNANCE_BLOCKER in result["promotion"]["reasons"]
    assert "no_automatic_promotion" in result["promotion"]["reasons"]
    assert before == after
