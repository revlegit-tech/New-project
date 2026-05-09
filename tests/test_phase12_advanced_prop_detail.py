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


def test_outlier_rail_hydrates_from_prop_detail_contract():
    source = (ROOT / "frontend" / "src" / "outlier" / "detail-rail" / "DetailRail.ts").read_text(encoding="utf-8")
    assert "Server drilldown" in source
    assert "priceComparison" in source
    assert "modelExplanation" in source
    assert "riskContext" in source


def test_board_passes_prop_side_identity_to_detail_lookup():
    source = (ROOT / "frontend" / "src" / "outlier" / "detail-rail" / "DetailRail.ts").read_text(encoding="utf-8")
    assert 'params.set("market", rowMarketKey(row))' in source
    assert 'params.set("player", rowPlayer(row))' in source
    assert 'params.set("line", text(rowLine(row), ""))' in source
    assert 'params.set("americanOdds", text(rowOdds(row), ""))' in source


def test_backend_detail_lookup_compares_prop_side_when_present():
    source = (ROOT / "mlb_app" / "services" / "prop_detail_service.py").read_text(encoding="utf-8")
    assert '"rawLabel"' in source
    assert "def _detail_side" in source
    assert "wanted_side" in source
    assert '"direction": _detail_side(row)' in source
