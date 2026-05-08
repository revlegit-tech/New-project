from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_advanced_prop_detail_modal_has_hit_rate_and_book_sections():
    source = (ROOT / "public" / "prop-detail.js").read_text(encoding="utf-8")
    assert "Advanced Prop Detail" in source
    assert "Hit-rate profile" in source
    assert "Recent game graph" in source
    assert "Sportsbook ladder" in source
    assert "Best of" in source
    assert "prop-detail-recent-table" in source


def test_outlier_rail_exposes_hit_rates_graph_and_books():
    source = (ROOT / "public" / "outlier-detail.js").read_text(encoding="utf-8")
    assert "ob-rail-game-graph" in source
    assert "Sportsbook Ladder" in source
    assert "ob-rail-hit-strip" in source
    assert "Best of" in source


def test_board_passes_prop_side_identity_to_detail_lookup():
    source = (ROOT / "public" / "outlier-board.js").read_text(encoding="utf-8")
    assert "rawLabel: row.rawLabel" in source
    assert "marketDisplay: row.marketDisplay" in source
    assert "season: row.season" in source


def test_backend_detail_lookup_compares_prop_side_when_present():
    source = (ROOT / "mlb_app" / "services" / "prop_detail_service.py").read_text(encoding="utf-8")
    assert '"rawLabel"' in source
    assert "def _detail_side" in source
    assert "wanted_side" in source
    assert '"direction": _detail_side(row)' in source
