from __future__ import annotations

import os
import time

from tools.ops.cleanup_generated_backups import cleanup, iter_candidates


def test_cleanup_generated_backups_dry_run_and_delete(tmp_path) -> None:
    backup = tmp_path / "data" / "playerboard" / "playerboard_2026.header_mismatch_20260508T181507Z.csv"
    backup.parent.mkdir(parents=True)
    backup.write_text("bad header\n", encoding="utf-8")
    old_timestamp = time.time() - 26 * 3600
    os.utime(backup, (old_timestamp, old_timestamp))

    candidates = iter_candidates(tmp_path, older_than_hours=24)
    assert [candidate.path for candidate in candidates] == [backup]

    assert cleanup(tmp_path, older_than_hours=24, dry_run=True) == 1
    assert backup.exists()

    assert cleanup(tmp_path, older_than_hours=24, dry_run=False) == 1
    assert not backup.exists()
