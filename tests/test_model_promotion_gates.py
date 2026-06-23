from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.model_registry_service import (
    ModelRegistryService,
    load_training_registry,
    save_training_registry,
)


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    model_dir = data_dir / "models"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=model_dir / "model_registry.json",
    )


def write_artifact_files(settings: Settings, *, artifact: bool = True, feature_schema: bool = True) -> tuple[str, str]:
    artifact_path = settings.root_dir / "data" / "models" / "artifacts" / "batter_hits" / "model.joblib"
    schema_path = settings.root_dir / "data" / "models" / "artifacts" / "batter_hits" / "feature_schema.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if artifact:
        artifact_path.write_bytes(b"test-model")
    if feature_schema:
        schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "test.features.v1",
                    "feature_names": ["feature_line", "feature_recent_rate"],
                    "required_features": ["feature_line", "feature_recent_rate"],
                }
            ),
            encoding="utf-8",
        )
    return (
        artifact_path.relative_to(settings.root_dir).as_posix(),
        schema_path.relative_to(settings.root_dir).as_posix(),
    )


def registry_entry(
    settings: Settings,
    *,
    status: str = "shadow",
    artifact: bool = True,
    feature_schema: bool = True,
    training_rows: int = 500,
    positive_rows: int = 100,
    calibrated: bool = True,
    model_key: str = "calibrated_logistic",
) -> dict[str, Any]:
    artifact_path, schema_path = write_artifact_files(settings, artifact=artifact, feature_schema=feature_schema)
    return {
        "status": status,
        "market": "batter_hits",
        "model_key": model_key,
        "selected_model": model_key,
        "version": "test-v1",
        "artifact": artifact_path,
        "features": schema_path,
        "training_rows": training_rows,
        "positive_rows": positive_rows,
        "negative_rows": max(training_rows - positive_rows, 0),
        "calibrated": calibrated,
        "production_gated": True,
    }


def actionnetwork_registry_entry(settings: Settings, **overrides: Any) -> dict[str, Any]:
    entry = registry_entry(settings)
    entry.update(
        {
            "source": "actionnetwork",
            "actionnetwork_forward_only": True,
            "clean_forward_days": 14,
            "event_confirmed_labels": 125,
            "diagnostic_rows": 0,
            "date_only_rows": 0,
            "reused_board_rows": 0,
            "push_rows": 0,
            "calibration_metrics_passed": True,
            "walk_forward_rows": 125,
            "shadow_roi_percent": 1.5,
            "min_shadow_roi_percent": 0.0,
        }
    )
    entry.update(overrides)
    return entry


def write_registry(settings: Settings, stage: str, entry: dict[str, Any]) -> None:
    settings.model_registry_path.parent.mkdir(parents=True, exist_ok=True)
    settings.model_registry_path.write_text(
        json.dumps({"batter_hits": {stage: entry}}, indent=2),
        encoding="utf-8",
    )


def reasons_for(settings: Settings, *, stage: str = "shadow", entry: dict[str, Any]) -> list[str]:
    write_registry(settings, stage, entry)
    return ModelRegistryService(settings).validate_promotion(
        "batter_hits",
        "production",
        source_status=stage,
    )["reasons"]


def test_missing_artifact_blocks_production(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, entry=registry_entry(settings, artifact=False))

    assert "missing_artifact" in reasons


def test_missing_feature_schema_blocks_production(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, entry=registry_entry(settings, feature_schema=False))

    assert "missing_feature_schema" in reasons


def test_low_training_rows_blocks_production(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, entry=registry_entry(settings, training_rows=499))

    assert "low_training_rows" in reasons


def test_low_positive_rows_blocks_production(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, entry=registry_entry(settings, positive_rows=99))

    assert "low_positive_rows" in reasons


def test_uncalibrated_model_blocks_production_when_required(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, entry=registry_entry(settings, calibrated=False))

    assert "calibration_required" in reasons


def test_candidate_to_production_direct_promotion_is_blocked(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, stage="candidate", entry=registry_entry(settings, status="candidate"))

    assert "candidate_to_production_blocked" in reasons
    assert "shadow_status_required" in reasons


def test_shadow_to_production_passes_when_all_gates_pass(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, "shadow", registry_entry(settings))

    validation = ModelRegistryService(settings).validate_promotion(
        "batter_hits",
        "production",
        source_status="shadow",
    )

    assert validation["allowed"] is True
    assert validation["reasons"] == []


def test_deprecated_model_cannot_be_promoted_directly(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, stage="deprecated", entry=registry_entry(settings, status="deprecated"))

    assert "deprecated_to_production_blocked" in reasons
    assert "shadow_status_required" in reasons


def test_transition_to_production_writes_validated_registry_stage(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, "shadow", registry_entry(settings))

    result = ModelRegistryService(settings).transition_model_status(
        "batter_hits",
        "production",
        source_status="shadow",
    )
    saved = json.loads(settings.model_registry_path.read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert saved["batter_hits"]["production"]["status"] == "production"
    assert saved["batter_hits"]["production"]["last_promoted_at"]


def test_actionnetwork_model_requires_clean_forward_days(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, entry=actionnetwork_registry_entry(settings, clean_forward_days=13))

    assert "min_clean_forward_days" in reasons


def test_actionnetwork_model_requires_event_confirmed_labels(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(settings, entry=actionnetwork_registry_entry(settings, event_confirmed_labels=99))

    assert "min_event_confirmed_labels" in reasons


def test_actionnetwork_model_blocks_diagnostic_date_only_reused_and_push_rows(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(
        settings,
        entry=actionnetwork_registry_entry(
            settings,
            diagnostic_rows=1,
            date_only_rows=1,
            reused_board_rows=1,
            push_rows=1,
        ),
    )

    assert "no_diagnostic_rows" in reasons
    assert "no_date_only_rows" in reasons
    assert "no_reused_board_rows" in reasons
    assert "no_push_rows" in reasons


def test_actionnetwork_model_blocks_weak_evaluation_metrics(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reasons = reasons_for(
        settings,
        entry=actionnetwork_registry_entry(
            settings,
            calibration_metrics_passed=False,
            walk_forward_rows=99,
            shadow_roi_percent=-0.1,
        ),
    )

    assert "calibration_metrics_failed" in reasons
    assert "walk_forward_sample_threshold" in reasons
    assert "shadow_roi_threshold" in reasons


def test_actionnetwork_clean_shadow_candidate_passes_extra_gates(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_registry(settings, "shadow", actionnetwork_registry_entry(settings))

    validation = ModelRegistryService(settings).validate_promotion(
        "batter_hits",
        "production",
        source_status="shadow",
    )

    assert validation["allowed"] is True
    assert validation["checks"]["actionnetwork"]["eventConfirmedLabels"] == 125


def test_registry_load_handles_missing_file(tmp_path: Path) -> None:
    assert load_training_registry(tmp_path / "missing.json") == {}


def test_registry_save_load_roundtrip_in_temp_dir(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry" / "model_registry.json"
    payload = {"batter_hits": {"candidate": {"status": "candidate", "market": "batter_hits"}}}

    save_training_registry(registry_path, payload)

    assert load_training_registry(registry_path) == payload
