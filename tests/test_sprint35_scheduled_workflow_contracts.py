from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_baseball_collector_scheduled_workflow_uses_bounded_safe_mode() -> None:
    source = Path(".github/workflows/season-collector.yml").read_text(encoding="utf-8")

    assert "execute_full_collection" in source
    assert "Scheduled runs always use safe daily mode" in source
    assert 'github.event_name }}" = "schedule"' in source
    assert "daily_ml_workflow.py --date" in source
    assert "timeout 20m python daily_ml_workflow.py" in source
    assert "COLLECTOR_EXIT=${PIPESTATUS[0]}" in source
    assert "continuing degraded so logs/artifacts can be inspected" in source
    assert "collector-status.env" in source
    assert "timeout 35m" in source
    assert "tools/validate_backup_files.py" in source


def test_baseball_collector_full_collection_path_remains_strict() -> None:
    source = Path(".github/workflows/season-collector.yml").read_text(encoding="utf-8")
    collector_step = source.split("- name: Run collector", 1)[1].split("- name: Run current-day OddsPapi team props", 1)[0]
    safe_branch = collector_step.split('if [ "${{ github.event_name }}" = "schedule" ] || [ "$EXECUTE_FULL" != "true" ]; then', 1)[1].split("else", 1)[0]
    full_branch = collector_step.split("else", 1)[1]

    assert "set +e" in safe_branch
    assert "COLLECTOR_EXIT=${PIPESTATUS[0]}" in safe_branch
    assert "timeout 35m" in full_branch
    assert "set +e" not in full_branch
    assert "|| true" not in full_branch


def test_weekly_repair_defaults_to_safe_dry_run_contract() -> None:
    source = Path(".github/workflows/weekly-data-repair.yml").read_text(encoding="utf-8")

    assert "execute:" in source
    assert 'default: "false"' in source
    assert "scripts/scheduled_weekly_repair.py --date" in source
    assert "season_auto_collector.py snapshot" not in source
    assert "github.event.inputs.execute == 'true'" in source
    assert "tools/validate_backup_files.py" in source
    assert "PYTHONPATH: ${{ github.workspace }}" in source
    assert "SUMMARY_EXIT=${PIPESTATUS[0]}" in source


def test_scheduled_workflows_do_not_require_live_apis_in_static_contracts() -> None:
    collector = Path(".github/workflows/season-collector.yml").read_text(encoding="utf-8")
    weekly = Path(".github/workflows/weekly-data-repair.yml").read_text(encoding="utf-8")

    assert "ODDSPAPI_KEY is not configured; skipping" in collector
    assert "PROPLINE_API_KEY" not in weekly
    assert "|| true" in collector


def test_scheduled_weekly_repair_executes_directly_from_repo_root(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/scheduled_weekly_repair.py",
            "--date",
            "2026-06-27",
            "--root",
            str(tmp_path),
        ],
        cwd=Path(".").resolve(),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / "health" / "weekly_repair_2026-06-27.json").is_file()
    assert not (tmp_path / "data" / "models").exists()
