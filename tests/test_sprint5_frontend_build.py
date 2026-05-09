from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
FRONTEND = ROOT / "frontend"


def test_vite_frontend_structure_exists() -> None:
    assert (ROOT / "vite.config.ts").exists()
    assert (FRONTEND / "index.html").exists()
    assert (FRONTEND / "legacy.html").exists()
    assert (FRONTEND / "src" / "outlier" / "main.ts").exists()
    assert (FRONTEND / "src" / "shared" / "markets" / "markets.ts").exists()
    assert (FRONTEND / "src" / "shared" / "styles" / "tokens.css").exists()


def test_package_scripts_include_vite_build() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["build"] == "vite build"
    assert package["scripts"]["dev"].startswith("vite")
    assert "vite" in package["devDependencies"]
    assert "typescript" in package["devDependencies"]


def test_public_index_is_outlier_only_and_fingerprinted() -> None:
    html = (PUBLIC / "index.html").read_text(encoding="utf-8")
    assert "legacyScripts" not in html
    assert "data-runtime-ui" not in html
    assert "/outlier-ui.js" not in html
    assert "/app.js" not in html
    assert re.search(r'/assets/outlier-[a-f0-9]{10}\.js', html)
    assert re.search(r'/assets/outlier-[a-f0-9]{10}\.css', html)


def test_legacy_entrypoint_is_isolated_from_outlier() -> None:
    html = (PUBLIC / "legacy.html").read_text(encoding="utf-8")
    assert "/app.js" in html
    assert "/trust-surface.js" in html
    assert "/outlier-ui.js" not in html
    assert "/outlier-core.js" not in html
    assert "data-runtime-ui=\"outlier\"" not in html


def test_markets_are_centralized_and_mlb_only_for_production() -> None:
    source = (FRONTEND / "src" / "shared" / "markets" / "markets.ts").read_text(encoding="utf-8")
    assert "export const MARKETS" in source
    assert 'key: "batter_hits"' in source
    assert 'sport: "MLB"' in source
    assert "MARKET_SELECT_OPTIONS" in source
    assert "productionUi" in source


def test_design_tokens_include_confidence_and_state_colors() -> None:
    tokens = (FRONTEND / "src" / "shared" / "styles" / "tokens.css").read_text(encoding="utf-8")
    for token in ["--color-bg", "--color-surface", "--color-positive", "--color-warning", "--color-danger", "--confidence-fresh", "--confidence-stale"]:
        assert token in tokens


def test_outlier_source_has_freshness_and_research_pick_controls() -> None:
    source = (FRONTEND / "src" / "outlier" / "main.ts").read_text(encoding="utf-8")
    assert "freshnessSurface" in source
    assert "Last collector run" in source
    assert "Odds freshness" in source
    assert "Schema version" in source
    assert "Add research pick" in source
    assert "stakeUnits: 0" in source
    assert "X-Baseball-Prop-Action" in source
    assert "Coming soon" in source
