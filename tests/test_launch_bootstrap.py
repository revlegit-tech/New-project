from __future__ import annotations

from datetime import date
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.launch_bootstrap_service import LaunchBootstrapService


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        db_path=data_dir / "state.sqlite3",
        current_season=2026,
    )


class FakeSnapshotWorkflow:
    def __init__(self, status: str = "success") -> None:
        self.calls = 0
        self.status = status

    def run(self, **_kwargs):
        self.calls += 1
        return {"status": self.status, "warnings": ["optional collector failed"] if self.status == "warning" else [], "outputs": {"saved_csv": "data/x.csv"}}


def test_bootstrap_skips_when_snapshot_is_fresh(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    snapshot = settings.data_dir / "warehouse" / "normalized" / "odds" / "actionnetwork_all_markets_2026-06-23.csv"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("header\n", encoding="utf-8")
    fake = FakeSnapshotWorkflow()

    payload = LaunchBootstrapService(settings, snapshot_workflow=fake).run(date_text="2026-06-23", today=date(2026, 6, 23))

    assert fake.calls == 0
    assert payload["status"] == "success"
    assert payload["steps"][0]["reason"] == "fresh"


def test_bootstrap_marks_warning_when_optional_collector_fails(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    fake = FakeSnapshotWorkflow(status="warning")

    payload = LaunchBootstrapService(settings, snapshot_workflow=fake).run(date_text="2026-06-23", today=date(2026, 6, 23))

    assert fake.calls == 1
    assert payload["status"] == "warning"
    assert "optional collector failed" in payload["warnings"]


def test_bootstrap_lock_blocks_overlap_and_stale_lock_recovers(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    lock = settings.data_dir / "status" / "launch_bootstrap.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("{}", encoding="utf-8")

    locked = LaunchBootstrapService(settings, snapshot_workflow=FakeSnapshotWorkflow()).run(date_text="2026-06-23", today=date(2026, 6, 23))
    assert locked["status"] == "skipped"

    import os
    old = 1
    os.utime(lock, (old, old))
    recovered = LaunchBootstrapService(settings, snapshot_workflow=FakeSnapshotWorkflow()).run(date_text="2026-06-23", today=date(2026, 6, 23))
    assert recovered["status"] == "warning"
    assert "Recovered stale lock" in " ".join(recovered["warnings"])
