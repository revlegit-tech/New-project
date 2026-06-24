from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_playerboard_default_prefers_current_day_active_snapshot() -> None:
    source = (ROOT / "mlb_app/services/playerboard_read_service.py").read_text(encoding="utf-8")

    assert "today_label = datetime.now().astimezone().date().isoformat()" in source
    assert "date_label=today_label" in source
    assert "today_result is not None and today_result.rows" in source
    assert "selected_date = self.snapshot_repository.latest_active_date(season)" in source

    today_index = source.index("today_label = datetime.now().astimezone().date().isoformat()")
    latest_active_index = source.index("selected_date = self.snapshot_repository.latest_active_date(season)")
    latest_warehouse_index = source.index("selected_date = self.db_snapshot_repository.latest_snapshot_date(season=season)")

    assert today_index < latest_active_index < latest_warehouse_index
