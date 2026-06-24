from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_playerboard_builder_respects_requested_limit_and_defaults_safe_workers() -> None:
    source = (ROOT / "mlb_app/services/playerboard_builder.py").read_text(encoding="utf-8")

    assert "load_limit = max(1, int(limit or 5000))" in source
    assert "limit=load_limit" in source
    assert 'os.environ.get("PLAYERBOARD_BUILD_WORKERS", "1")' in source
    assert "if max_workers <= 1:" in source
    assert "ThreadPoolExecutor" in source
