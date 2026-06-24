from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_season_auto_collector_uses_safe_daily_playerboard_build() -> None:
    source = (ROOT / "season_auto_collector.py").read_text(encoding="utf-8")

    assert 'PLAYERBOARD_DAILY_BUILD_LIMIT", "1000"' in source
    assert 'PLAYERBOARD_DAILY_SOURCE_MODE", "propline"' in source
    assert "limit=playerboard_limit" in source
    assert "source_mode=playerboard_source_mode" in source
    assert 'source_mode="canonical"' not in source


def test_daily_ml_workflow_uses_safe_playerboard_rebuild_query() -> None:
    source = (ROOT / "daily_ml_workflow.py").read_text(encoding="utf-8")

    assert "limit=1000" in source
    assert "refresh=1" in source
    assert "save=1" in source
    assert "replaceDate=1" in source
    assert "sourceMode=propline" in source
