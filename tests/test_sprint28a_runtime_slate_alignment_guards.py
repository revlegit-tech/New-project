from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def test_default_playerboard_resolves_latest_db_snapshot_before_csv_fallback() -> None:
    source = _source("mlb_app/services/playerboard_read_service.py")

    assert "selected_date = self.db_snapshot_repository.latest_snapshot_date(season=season)" in source
    assert "date_label=selected_date" in source
    assert "return self.repository.read_current_playerboard(season=season, date_label=selected_date, market=market)" in source


def test_default_edge_board_does_not_prefer_saved_edge_snapshot_without_date() -> None:
    source = _source("mlb_app/services/edge_board_service.py")

    assert 'if not _bypass_board_cache(query) and _query_value(query, "date"):' in source
