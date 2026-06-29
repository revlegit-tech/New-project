from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.contracts.feature_store_schema import pregame_feature_names
from mlb_app.services.baseline_model_training_service import BaselineModelTrainingService, _feature_columns


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


def baseline_feature(date_label: str, **overrides: Any) -> dict[str, Any]:
    row = {field: "" for field in pregame_feature_names()}
    row.update(
        {
            "date": date_label,
            "season": 2026,
            "player": "Join Player",
            "team": "",
            "opponent": "",
            "market": "batter_total_bases",
            "side": "Over",
            "line": "1.5",
            "book_count": "2",
            "implied_probability_percent": "52.5",
            "hit_rate_10": "0.5",
        }
    )
    row.update(overrides)
    return row


def baseline_label(date_label: str, **overrides: Any) -> dict[str, Any]:
    row = {
        "date": date_label,
        "season": 2026,
        "player": "Join Player",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_total_bases",
        "side": "Over",
        "line": "1.5",
        "result": "hit",
        "hit": "1",
    }
    row.update(overrides)
    return row


def joined_rows(settings: Settings, date_label: str, feature_rows: list[dict[str, Any]], label_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    write_csv(settings.data_dir / "features" / f"prop_features_{date_label}.csv", feature_rows, fieldnames=pregame_feature_names())
    write_csv(settings.data_dir / "training" / "player_prop_labels_2026.csv", label_rows)
    return BaselineModelTrainingService(settings)._joined_rows(target_date=date_label, season=2026, market="batter_total_bases", label_files=[])


def test_baseline_join_matches_prop_key(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"

    rows = joined_rows(
        settings,
        date_label,
        [baseline_feature(date_label, prop_key="prop-1", player="Wrong Name", line="2.5")],
        [baseline_label(date_label, prop_key="prop-1", player="Join Player", line="1.5", hit="1", result="hit")],
    )

    assert len(rows) == 1
    assert rows[0]["__target"] == 1


def test_baseline_join_matches_source_row_id(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"

    rows = joined_rows(
        settings,
        date_label,
        [baseline_feature(date_label, source_row_id="row-1", player="Wrong Name", line="2.5")],
        [baseline_label(date_label, source_row_id="row-1", player="Join Player", line="1.5", hit="0", result="miss")],
    )

    assert len(rows) == 1
    assert rows[0]["__target"] == 0


def test_baseline_join_uses_unique_player_market_line_fallback_without_ids(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"

    rows = joined_rows(
        settings,
        date_label,
        [baseline_feature(date_label, player="Join Player", team="", side="", line="1.5")],
        [baseline_label(date_label, player="Join Player", team="NYY", side="Over", line="1.5")],
    )

    assert len(rows) == 1


def test_baseline_join_does_not_join_ambiguous_fallback(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"

    rows = joined_rows(
        settings,
        date_label,
        [baseline_feature(date_label, player="Join Player", team="", side="", line="1.5")],
        [
            baseline_label(date_label, player="Join Player", prop_key="label-1", side="Over", line="1.5"),
            baseline_label(date_label, player="Join Player", prop_key="label-2", side="Under", line="1.5", hit="0", result="miss"),
        ],
    )

    assert rows == []


def test_baseline_feature_columns_exclude_identity_columns() -> None:
    row = baseline_feature(
        "2026-06-24",
        source_row_id="123",
        prop_key="456",
        player_id="789",
        season="2026",
        game_pk="100",
    )
    columns = _feature_columns([{**row, "__target": 1}])

    assert "hit_rate_10" in columns
    assert {"source_row_id", "prop_key", "player_id", "playerId", "season", "game_pk", "team", "opponent", "player"}.isdisjoint(columns)


def test_baseline_dry_run_reports_candidate_train_and_test_rows_for_matching_fixture(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    date_label = "2026-06-24"
    features = []
    labels = []
    for index in range(20):
        player = f"Join Player {index}"
        features.append(baseline_feature(date_label, player=player, line="1.5", hit_rate_10=str(index / 20)))
        labels.append(baseline_label(date_label, player=player, line="1.5", hit=str(index % 2), result="hit" if index % 2 else "miss"))
    write_csv(settings.data_dir / "features" / f"prop_features_{date_label}.csv", features, fieldnames=pregame_feature_names())
    write_csv(settings.data_dir / "training" / "player_prop_labels_2026.csv", labels)
    monkeypatch.setattr(
        "mlb_app.services.data_source_capability_service.DataSourceCapabilityService.audit_feature_availability",
        lambda self, date_label, season: {"missingCriticalFeatureGroups": []},
    )

    payload = BaselineModelTrainingService(settings).train(date_label=date_label, season=2026, market="batter_total_bases", train=False)

    assert payload["artifactWritten"] is False
    assert payload["metrics"]["candidateRows"] == 20
    assert payload["metrics"]["trainRows"] > 0
    assert payload["metrics"]["testRows"] > 0
    assert payload["featureColumns"]


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
