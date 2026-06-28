from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.contracts.feature_store_schema import pregame_feature_names
from mlb_app.services.model_training_readiness_service import ModelTrainingReadinessService


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_feature_matrix(settings: Settings, date_label: str) -> None:
    row = {field: "" for field in pregame_feature_names()}
    row.update({"date": date_label, "season": 2026, "prop_key": "p1", "player": "A", "team": "NYY", "market": "batter_hits", "line": "0.5"})
    write_csv(settings.data_dir / "features" / f"prop_features_{date_label}.csv", [row], fieldnames=pregame_feature_names())


def test_pushes_and_voids_do_not_satisfy_two_class_target(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_feature_matrix(settings, date_label)
    rows = [{"date": date_label, "market": "batter_hits", "result": "push", "hit": "0"} for _ in range(20)]
    rows += [{"date": date_label, "market": "batter_hits", "result": "void", "hit": ""} for _ in range(20)]
    write_csv(settings.data_dir / "labels" / "player_prop_labels_2026.csv", rows)
    monkeypatch.setattr(ModelTrainingReadinessService, "_has_artifacts", lambda self, kind: False)

    payload = ModelTrainingReadinessService(settings).payload(date_label=date_label, season=2026, market="batter_hits")
    market = payload["markets"][0]

    assert market["pushRows"] == 20
    assert market["voidRows"] == 20
    assert market["hitRows"] == 0
    assert market["missRows"] == 0
    assert market["twoClassTarget"] is False


def test_market_specific_hit_miss_labels_can_make_baseline_eligible(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    write_feature_matrix(settings, date_label)
    rows = [
        {"date": date_label, "market": "batter_hits", "result": "hit" if index % 2 else "miss", "hit": "1" if index % 2 else "0"}
        for index in range(100)
    ]
    write_csv(settings.data_dir / "training" / "player_prop_labels_2026.csv", rows)
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )

    payload = ModelTrainingReadinessService(settings).payload(date_label=date_label, season=2026, market="batter_hits")
    market = payload["markets"][0]

    assert market["market"] == "batter_hits"
    assert market["labelRows"] == 100
    assert market["twoClassTarget"] is True
    assert market["baselineEligible"] is True
    assert market["productionEligible"] is False
    assert payload["readyForProductionTraining"] is False
