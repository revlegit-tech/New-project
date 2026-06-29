from __future__ import annotations

from pathlib import Path


def test_baseball_collector_scheduled_workflow_uses_bounded_safe_mode() -> None:
    source = Path(".github/workflows/season-collector.yml").read_text(encoding="utf-8")

    assert "execute_full_collection" in source
    assert "Scheduled runs always use safe daily mode" in source
    assert 'github.event_name }}" = "schedule"' in source
    assert "daily_ml_workflow.py --date" in source
    assert "timeout 20m python daily_ml_workflow.py" in source
    assert "timeout 35m" in source
    assert "tools/validate_backup_files.py" in source


def test_weekly_repair_defaults_to_safe_dry_run_contract() -> None:
    source = Path(".github/workflows/weekly-data-repair.yml").read_text(encoding="utf-8")

    assert "execute:" in source
    assert 'default: "false"' in source
    assert "scripts/scheduled_weekly_repair.py --date" in source
    assert "season_auto_collector.py snapshot" not in source
    assert "github.event.inputs.execute == 'true'" in source
    assert "tools/validate_backup_files.py" in source


def test_scheduled_workflows_do_not_require_live_apis_in_static_contracts() -> None:
    collector = Path(".github/workflows/season-collector.yml").read_text(encoding="utf-8")
    weekly = Path(".github/workflows/weekly-data-repair.yml").read_text(encoding="utf-8")

    assert "ODDSPAPI_KEY is not configured; skipping" in collector
    assert "PROPLINE_API_KEY" not in weekly
    assert "|| true" in collector
