from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scripts.build_historical_prop_training_from_labels import build_historical_training, read_csv


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def label(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-22",
        "season": "2026",
        "source_row_id": "source-1",
        "prop_key": "prop-1",
        "player": "Join Player",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_hits",
        "side": "Over",
        "line": "0.5",
        "actual_value": "1",
        "result": "hit",
        "hit": "true",
        "push": "false",
        "void": "false",
        "label_status": "graded",
    }
    row.update(overrides)
    return row


def feature(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-22",
        "season": "2026",
        "source_row_id": "source-1",
        "prop_key": "prop-1",
        "player": "Join Player",
        "team": "NYY",
        "opponent": "BAL",
        "market": "batter_hits",
        "side": "Over",
        "line": "0.5",
        "book": "DraftKings",
        "american_odds": "-110",
        "implied_probability_percent": "52.38",
        "game_market_available": "true",
    }
    row.update(overrides)
    return row


def run_builder(tmp_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    return build_historical_training(
        season=2026,
        start_date="2026-06-22",
        end_date="2026-06-22",
        labels_dir=tmp_path / "labels",
        features_dir=tmp_path / "features",
        training_dir=tmp_path / "training",
        playerboard=tmp_path / "playerboard_2026.csv",
        out=tmp_path / "out.csv",
        summary_out=tmp_path / "summary.json",
        dry_run=dry_run,
    )


def test_excludes_push_and_void_rows(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "labels" / "player_prop_labels_2026-06-22.csv",
        [
            label(prop_key="push", source_row_id="push", actual_value="0.5", result="push", push="true"),
            label(prop_key="void", source_row_id="void", result="void", void="true"),
            label(prop_key="ok", source_row_id="ok"),
        ],
    )
    write_csv(tmp_path / "features" / "player_prop_features_2026-06-22.csv", [feature(prop_key="ok", source_row_id="ok")])

    summary = run_builder(tmp_path)

    assert summary["labels_used"] == 1
    assert summary["labels_skipped_by_reason"]["push"] == 1
    assert summary["labels_skipped_by_reason"]["void"] == 1
    assert len(read_csv(tmp_path / "out.csv")) == 1


def test_outcome_conversion_prefers_actual_value_and_line(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "labels" / "player_prop_labels_2026-06-22.csv",
        [
            label(prop_key="over", source_row_id="over", actual_value="2", line="1.5", result="loss", hit="false"),
            label(prop_key="under", source_row_id="under", actual_value="1", line="1.5", result="hit", hit="true"),
        ],
    )
    write_csv(
        tmp_path / "features" / "player_prop_features_2026-06-22.csv",
        [
            feature(prop_key="over", source_row_id="over", line="1.5"),
            feature(prop_key="under", source_row_id="under", line="1.5"),
        ],
    )

    run_builder(tmp_path)
    rows = {row["prop_key"]: row for row in read_csv(tmp_path / "out.csv")}

    assert rows["over"]["over"] == "1"
    assert rows["over"]["result"] == "win"
    assert rows["under"]["over"] == "0"
    assert rows["under"]["result"] == "loss"


def test_join_key_priority_uses_prop_key_before_composite_match(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "labels" / "player_prop_labels_2026-06-22.csv",
        [label(prop_key="winner", source_row_id="", player="Real Player", team="NYY", line="1.5")],
    )
    write_csv(
        tmp_path / "features" / "player_prop_features_2026-06-22.csv",
        [
            feature(prop_key="wrong", source_row_id="", player="Real Player", team="NYY", line="1.5", american_odds="-105"),
            feature(prop_key="winner", source_row_id="", player="Different Player", team="BOS", line="9.5", american_odds="+125"),
        ],
    )

    run_builder(tmp_path)
    rows = read_csv(tmp_path / "out.csv")

    assert rows[0]["prop_key"] == "winner"
    assert rows[0]["american_odds"] == "+125"
    assert rows[0]["join_method"] == "prop_key"


def test_fallback_playerboard_join(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "labels" / "player_prop_labels_2026-06-22.csv",
        [label(prop_key="pb-prop", source_row_id="pb-source", line="1.5")],
    )
    write_csv(
        tmp_path / "playerboard_2026.csv",
        [
            {
                "date": "2026-06-22",
                "season": "2026",
                "propKey": "pb-prop",
                "id": "pb-source",
                "player": "Join Player",
                "team": "NYY",
                "opponent": "BAL",
                "market": "batter_hits",
                "rawLabel": "Over",
                "line": "1.5",
                "book": "FanDuel",
                "americanOdds": "-120",
            }
        ],
    )

    summary = run_builder(tmp_path)
    rows = read_csv(tmp_path / "out.csv")

    assert summary["labels_used"] == 1
    assert rows[0]["book"] == "FanDuel"
    assert rows[0]["american_odds"] == "-120"


def test_no_leakage_columns_in_output(tmp_path: Path) -> None:
    write_csv(tmp_path / "labels" / "player_prop_labels_2026-06-22.csv", [label()])
    write_csv(
        tmp_path / "features" / "player_prop_features_2026-06-22.csv",
        [feature(actual_value="99", result="win", hit="true", target_result="win", feature_line="0.5")],
    )

    run_builder(tmp_path)
    rows = read_csv(tmp_path / "out.csv")

    assert rows[0]["line"] == "0.5"
    assert "actual_value" not in rows[0]
    assert "hit" not in rows[0]
    assert "target_result" not in rows[0]
    assert "feature_line" not in rows[0]


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    write_csv(tmp_path / "labels" / "player_prop_labels_2026-06-22.csv", [label()])
    write_csv(tmp_path / "features" / "player_prop_features_2026-06-22.csv", [feature()])

    summary = run_builder(tmp_path, dry_run=True)

    assert summary["candidate_rows"] == 1
    assert summary["rows_written"] == 0
    assert not (tmp_path / "out.csv").exists()
    assert not (tmp_path / "summary.json").exists()
