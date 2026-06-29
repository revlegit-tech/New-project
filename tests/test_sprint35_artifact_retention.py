from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prune_old_artifacts import build_report


def touch_old(path: Path, *, days: int = 60) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("artifact\n", encoding="utf-8")
    old = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    path.touch()
    import os

    os.utime(path, (old, old))


def test_retention_dry_run_does_not_delete(tmp_path: Path) -> None:
    old_report = tmp_path / "data" / "reports" / "old.json"
    touch_old(old_report)

    report = build_report(root=tmp_path, keep_days=30, execute=False)

    assert report["dryRun"] is True
    assert "data/reports/old.json" in report["candidates"]
    assert report["deleted"] == []
    assert old_report.exists()


def test_retention_execute_deletes_only_allowed_old_files_and_keeps_latest(tmp_path: Path) -> None:
    old_report = tmp_path / "data" / "reports" / "old.json"
    outside_file = tmp_path / "tests" / "old_fixture.csv"
    old_board = tmp_path / "data" / "playerboard" / "playerboard_2025.csv"
    latest_board = tmp_path / "data" / "playerboard" / "playerboard_2026.csv"
    touch_old(old_report)
    touch_old(outside_file)
    touch_old(old_board, days=90)
    touch_old(latest_board, days=80)

    report = build_report(root=tmp_path, keep_days=30, execute=True)

    assert report["dryRun"] is False
    assert not old_report.exists()
    assert outside_file.exists()
    assert old_board.exists() is False
    assert latest_board.exists()
    assert "data/playerboard/playerboard_2026.csv" in report["skipped"]


def test_retention_defaults_to_dry_run_in_cli_source() -> None:
    source = Path("scripts/prune_old_artifacts.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--dry-run", action="store_true")' in source
    assert 'parser.add_argument("--execute", action="store_true")' in source
    assert "execute=bool(args.execute)" in source
