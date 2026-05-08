from __future__ import annotations

from tools.phase15_common import dedupe_key, label_value, summarize_training_rows
from tools.phase15_build_quality_dataset import choose_rows


def test_label_value_understands_common_outcomes():
    assert label_value({"over": "1"}) == 1
    assert label_value({"target": "0"}) == 0
    assert label_value({"result": "hit"}) == 1
    assert label_value({"result": "miss"}) == 0
    assert label_value({"result": ""}) is None


def test_summarize_training_rows_counts_two_class_labels():
    rows = [{"over": "1"}, {"over": "0"}, {"over": "0"}, {"over": ""}]
    summary = summarize_training_rows(rows)
    assert summary["rows"] == 4
    assert summary["labeledRows"] == 3
    assert summary["positiveRows"] == 1
    assert summary["negativeRows"] == 2
    assert summary["twoClass"] is True


def test_dedupe_key_keeps_market_and_line_identity():
    row = {"date": "2026-05-07", "player": "Manny Machado", "market": "batter_hits", "line": "0.5", "rawLabel": "Over"}
    assert dedupe_key(row, "batter_hits") == ("2026-05-07", "manny machado", "batter_hits", "0.5", "over")
