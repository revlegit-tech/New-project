from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.services.shadow_artifact_freshness_service import ShadowArtifactFreshnessService
from mlb_app.services.shadow_model_summary_service import SHADOW_MARKETS, ShadowModelSummaryService


ROOT = Path(__file__).resolve().parents[1]


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_registry(settings: Settings, markets: tuple[str, ...] = SHADOW_MARKETS) -> None:
    registry = {
        market: {
            "candidate": {"status": "candidate", "model_key": "random_forest"},
            "shadow": {
                "status": "shadow",
                "selected_model": "calibrated_logistic",
                "model_key": "calibrated_logistic",
                "version": "sprint19-20260704T050002Z",
                "artifact": str(settings.data_dir / "models" / "artifacts" / "sprint19" / market / "model.joblib"),
                "positive_rows": 101,
                "negative_rows": 149,
            },
        }
        for market in markets
    }
    write_json(settings.model_registry_path, registry)


def write_shadow_market(
    settings: Settings,
    market: str,
    *,
    generated_at: str | None = "2099-07-04T05:47:37+00:00",
    fallback_used: bool | None = False,
) -> None:
    artifact_dir = settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic" / market
    common = {
        "market": market,
        "modelStage": "shadow",
        "modelKey": "calibrated_logistic",
        "sourcePath": f"data/warehouse/ml_features/{market}.csv",
        "validationDates": ["2026-06-23", "2026-06-24"],
    }
    if generated_at is not None:
        common["generatedAt"] = generated_at
    if fallback_used is not None:
        common["fallbackUsed"] = fallback_used
    write_json(
        artifact_dir / "backtest_metrics.json",
        {
            **common,
            "evaluatedRows": 250,
            "positiveRows": 101,
            "negativeRows": 149,
            "auc": 0.61,
            "brierScore": 0.22,
            "logLoss": 0.63,
        },
    )
    write_json(
        artifact_dir / "calibration.json",
        {
            **common,
            "sampleCount": 250,
            "brierScore": 0.22,
            "logLoss": 0.63,
            "expectedCalibrationError": 0.11,
        },
    )
    write_json(
        artifact_dir / "shadow_manifest.json",
        {
            **common,
            "backtestStatus": "ready",
            "calibrationStatus": "ready",
        },
    )


def test_shadow_freshness_endpoint_reports_four_markets_and_research_locks(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    for market in SHADOW_MARKETS:
        write_shadow_market(settings, market)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/ml-models/shadow-freshness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "shadow-artifact-freshness.v1"
    assert payload["marketCount"] == 4
    assert {row["market"] for row in payload["markets"]} == set(SHADOW_MARKETS)
    for row in payload["markets"]:
        assert row["action"] == "Research"
        assert row["readinessLabel"] == "Experimental"
        assert row["stakeUnits"] == 0
        assert row["betActionAllowed"] is False


def test_missing_generated_at_is_unknown_without_fabricated_timestamp(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    write_shadow_market(settings, "batter_hits", generated_at=None)

    row = ShadowArtifactFreshnessService(settings).payload(market="batter_hits")["markets"][0]

    assert row["freshnessStatus"] == "unknown"
    assert row["generatedAt"] == ""
    assert row["latestValidationDate"] == "2026-06-24"
    assert any("generatedAt is missing" in warning for warning in row["warnings"])


def test_missing_artifacts_and_registry_pointer_block_without_crash(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    row = ShadowArtifactFreshnessService(settings).payload(market="batter_hits")["markets"][0]

    assert row["artifactStatus"] == "missing"
    assert row["freshnessStatus"] == "missing"
    assert "missing_shadow_backtest" in row["blockers"]
    assert "missing_registry_shadow_pointer" in row["blockers"]


def test_fallback_used_true_is_reported_by_freshness_and_summary(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, ("batter_hits",))
    write_shadow_market(settings, "batter_hits", fallback_used=True)

    freshness = ShadowArtifactFreshnessService(settings).payload(market="batter_hits")["markets"][0]
    summary = ShadowModelSummaryService(settings).payload(market="batter_hits")["markets"][0]

    assert freshness["fallbackUsed"] is True
    assert "fallback_used" in freshness["blockers"]
    assert summary["provenance"]["fallbackUsed"] is True


def test_registry_shadow_pointer_missing_blocks_freshness(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_shadow_market(settings, "batter_hits")

    row = ShadowArtifactFreshnessService(settings).payload(market="batter_hits")["markets"][0]

    assert row["registryShadowPointerPresent"] is False
    assert "missing_registry_shadow_pointer" in row["blockers"]


def test_existing_shadow_safety_endpoint_counts_remain_locked(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings)
    for market in SHADOW_MARKETS:
        write_shadow_market(settings, market)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    summary = client.get("/api/ml-models/shadow-summary").json()
    readiness = client.get("/api/ml-models/shadow-readiness").json()
    gates = client.get("/api/ml-models/production-gates").json()

    assert summary["marketCount"] == 4
    assert summary["readyMarketCount"] == 4
    assert readiness["marketCount"] == 4
    assert readiness["readyMarketCount"] == 0
    assert readiness["blockedMarketCount"] == 4
    assert gates["marketCount"] == 4
    assert gates["readyMarketCount"] == 0
    assert gates["blockedMarketCount"] == 4
    for row in readiness["markets"]:
        assert row["productionEligible"] is False
        assert "manual_governance_review_required" in row["blockers"]


def test_daily_pipeline_contains_shadow_freshness_audit_without_promote_call() -> None:
    source = (ROOT / "scripts" / "run_mlb_full_daily_pipeline.ps1").read_text(encoding="utf-8")

    assert "Shadow model audit" in source
    assert "/api/ml-models/shadow-freshness" in source
    assert "productionPromotion=false" in source
    assert "/api/admin/ml-models/promote" not in source


def test_ui_static_freshness_labels_render_without_action_buttons() -> None:
    detail = (ROOT / "frontend" / "src" / "outlier" / "detail-rail" / "DetailRail.ts").read_text(encoding="utf-8")
    client = (ROOT / "frontend" / "src" / "outlier" / "api" / "client.ts").read_text(encoding="utf-8")

    assert "/api/ml-models/shadow-freshness" in client
    for label in ["Freshness status", "Generated at", "Artifact age", "Latest validation date", "Freshness warnings"]:
        assert label in detail
    assert "data-action: \"promote" not in detail
    assert "Bet Now" not in detail
