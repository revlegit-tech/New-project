from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def test_manual_snapshot_runs_incremental_stats_catchup() -> None:
    source = _source("season_auto_collector.py")

    block = re.search(
        r'if\s+run_type\s+in\s+\{"midnight",\s*"manual"\}:\s*'
        r'try:\s*'
        r'from\s+incremental_stats_collector\s+import\s+catchup_stats'
        r'(?P<body>.*?)'
        r'except\s+Exception\s+as\s+stats_error:',
        source,
        re.DOTALL,
    )

    assert block is not None
    assert 'summary["incrementalStats"] = catchup_stats(' in block.group("body")


def test_manual_snapshot_replaces_same_date_playerboard_rows() -> None:
    source = _source("season_auto_collector.py")

    block = re.search(
        r'summary\["playerboard"\]\s*=\s*build_playerboard\('
        r'(?P<args>.*?)'
        r'\)\s*'
        r'except\s+Exception\s+as\s+board_error:',
        source,
        re.DOTALL,
    )

    assert block is not None
    assert "replace_date=True" in block.group("args")


def test_build_playerboard_forwards_replace_date_to_save() -> None:
    source = " ".join(_source("mlb_app/services/playerboard_builder.py").split())

    assert (
        "save_playerboard_snapshot(season, date_label, top_cards, "
        "replace_date=replace_date, market=market)"
    ) in source
