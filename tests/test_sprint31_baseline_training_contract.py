from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.contracts.feature_store_schema import pregame_feature_names
from mlb_app.services.baseline_model_training_service import BaselineModelTrainingService


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_training_fixtures(settings: Settings, date_label: str) -> None:
    feature_rows = []
    label_rows = []
    for index in range(100):
        player = f"Player {index}"
        hit = index % 2
        row = {field: "" for field in pregame_feature_names()}
        row.update(
            {
                "date": date_label,
                "season": 2026,
                "player": player,
                "team": "NYY",
                "opponent": "BAL",
                "market": "batter_hits",
                "line": "0.5",
                "book_count": "2",
                "implied_probability_percent": "52.5",
                "hit_rate_10": str(index / 100),
            }
        )
        feature_rows.append(row)
        label_rows.append(
            {
                "date": date_label,
                "season": 2026,
                "player": player,
                "team": "NYY",
                "market": "batter_hits",
                "line": "0.5",
                "result": "hit" if hit else "miss",
                "hit": str(hit),
            }
        )
    write_csv(settings.data_dir / "features" / f"prop_features_{date_label}.csv", feature_rows, fieldnames=pregame_feature_names())
    write_csv(settings.data_dir / "training" / "player_prop_labels_2026.csv", label_rows)


def test_baseline_dry_run_does_not_write_artifacts(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_training_fixtures(settings, date_label)
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )

    payload = BaselineModelTrainingService(settings).train(date_label=date_label, season=2026, market="batter_hits", train=False)

    assert payload["dryRun"] is True
    assert payload["modelTrainingTriggered"] is False
    assert payload["externalApiCallsMade"] is False
    assert payload["readyForProductionTraining"] is False
    assert not (settings.data_dir / "models" / "baseline" / "batter_hits").exists()


def test_xgboost_missing_does_not_crash_or_write(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_training_fixtures(settings, date_label)
    monkeypatch.setattr("mlb_app.services.baseline_model_training_service.importlib.util.find_spec", lambda name: None if name == "xgboost" else object())
    monkeypatch.setattr(
        "mlb_app.services.model_training_readiness_service.importlib.util.find_spec",
        lambda name: None if name == "xgboost" else object(),
    )
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )

    payload = BaselineModelTrainingService(settings).train(date_label=date_label, season=2026, market="batter_hits", train=True)

    assert payload["modelState"] == "unavailable"
    assert payload["modelTrainingTriggered"] is False
    assert payload["artifactWritten"] is False
    assert any("xgboost is unavailable" in warning for warning in payload["warnings"])
