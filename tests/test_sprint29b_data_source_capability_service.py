from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.data_source_capability_service import DataSourceCapabilityService, audit_feature_availability


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    return replace(settings, data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) or ["date"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def seed_board_ready_sources(settings: Settings, date_label: str) -> None:
    write_csv(settings.data_dir / "odds" / f"propline_props_{date_label}.csv", [{"date": date_label, "market": "batter_hits"}])
    write_csv(settings.data_dir / "warehouse" / "game_context" / f"mlb_schedule_{date_label}.json", [{"date": date_label}])
    write_csv(settings.data_dir / "cache" / "weather" / "weather_features_2026.csv", [{"gamePk": "1"}])
    write_csv(settings.data_dir / "cloud" / "season_logs" / "batter_game_logs_2026.csv", [{"date": date_label, "player": "A"}])
    write_csv(settings.data_dir / "cloud" / "season_logs" / "pitcher_game_logs_2026.csv", [{"date": date_label, "player": "P"}])
    write_csv(settings.data_dir / "playerboard" / "playerboard_2026.csv", [{"date": date_label, "player": "A"}])


def test_source_capability_report_returns_schema_and_known_sources(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_csv(settings.data_dir / "odds" / f"propline_props_{date_label}.csv", [{"date": date_label, "market": "batter_hits"}])
    write_csv(settings.data_dir / "cache" / "weather" / "weather_features_2026.csv", [{"gamePk": "1", "weather_temperature_f": "72"}])
    write_csv(settings.data_dir / "cloud" / "season_logs" / "batter_game_logs_2026.csv", [{"date": date_label, "player": "A"}])
    write_csv(settings.data_dir / "cloud" / "season_logs" / "pitcher_game_logs_2026.csv", [{"date": date_label, "player": "P"}])

    payload = DataSourceCapabilityService(settings).payload(date_label=date_label, season=2026)

    assert payload["schemaVersion"] == "data-source-capability.v1"
    assert payload["status"] in {"ok", "partial"}
    assert {"proplineProps", "actionNetworkOdds", "gameMarkets", "theOddsApi", "oddsPapi", "mlbStatsApi", "weather", "savant", "umpires", "playerboard", "labels"} <= set(payload["sources"])
    assert payload["sources"]["proplineProps"]["available"] is True
    assert payload["featureGroups"]["market"]["available"] is True
    assert payload["featureAudit"]["modelTrainingTriggered"] is False


def test_missing_source_files_produce_partial_not_exception(tmp_path: Path) -> None:
    payload = DataSourceCapabilityService(make_settings(tmp_path)).payload(date_label="2026-06-24", season=2026)

    assert payload["schemaVersion"] == "data-source-capability.v1"
    assert payload["status"] == "partial"
    assert payload["sources"]["proplineProps"]["status"] == "missing"
    assert "market" in payload["featureAudit"]["missingCriticalFeatureGroups"]


def test_audit_feature_availability_reports_board_and_training_readiness(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    seed_board_ready_sources(settings, date_label)

    audit = audit_feature_availability(date_label, 2026, settings=settings)

    assert audit["schemaVersion"] == "feature-availability-audit.v1"
    assert audit["readyForBoard"] is True
    assert audit["readyForFeatureStore"] is True
    assert audit["readyForBaselineTraining"] is False
    assert audit["readyForProductionTraining"] is False
    assert audit["readyForMLTraining"] is False
    assert "labels" in audit["missingFeatureGroups"]


def test_tiny_labels_do_not_make_baseline_training_ready(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    seed_board_ready_sources(settings, date_label)
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", [{"date": date_label, "market": "batter_hits", "result": "win", "hit": "1"}])

    payload = DataSourceCapabilityService(settings).payload(date_label=date_label, season=2026)
    audit = payload["featureAudit"]

    assert audit["readyForBoard"] is True
    assert audit["readyForFeatureStore"] is True
    assert audit["labelSufficiency"]["labelsAvailable"] is True
    assert audit["labelSufficiency"]["totalLabelRows"] == 1
    assert audit["labelSufficiency"]["baselineMinRows"] == 100
    assert audit["readyForBaselineTraining"] is False
    assert audit["readyForProductionTraining"] is False
    assert any("Label row count is below baseline threshold" in item for item in payload["recommendations"])


def test_production_training_false_without_market_two_class_and_calibration_validation(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    seed_board_ready_sources(settings, date_label)
    rows = [
        {"date": date_label, "market": "batter_hits", "result": "win" if index % 2 else "loss", "hit": str(index % 2)}
        for index in range(100)
    ]
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", rows)

    payload = DataSourceCapabilityService(settings).payload(date_label=date_label, season=2026)
    audit = payload["featureAudit"]

    assert audit["readyForBaselineTraining"] is True
    assert audit["trainingValidation"]["perMarketLabelValidationAvailable"] is False
    assert audit["trainingValidation"]["twoClassTargetValidationAvailable"] is False
    assert audit["trainingValidation"]["calibrationArtifactsAvailable"] is False
    assert audit["trainingValidation"]["backtestArtifactsAvailable"] is False
    assert audit["readyForProductionTraining"] is False
    assert any("Production training requires per-market two-class validation and calibration" in item for item in payload["recommendations"])


def test_data_source_audit_does_not_call_external_apis_or_train(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("audit must not collect data or train models")

    monkeypatch.setattr("mlb_app.integrations.statsapi.warehouse_sync.sync_date", forbidden)
    monkeypatch.setattr("mlb_app.services.model_training_service.ModelTrainingService.train_market", forbidden)

    payload = DataSourceCapabilityService(make_settings(tmp_path)).payload(date_label="2026-06-24", season=2026)

    assert payload["featureAudit"]["externalApiCallsMade"] is False
    assert payload["featureAudit"]["modelTrainingTriggered"] is False
