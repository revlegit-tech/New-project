from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
FRONTEND = ROOT / "frontend" / "src" / "outlier"


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def read_frontend(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def load_safety_linter():
    spec = importlib.util.spec_from_file_location("lint_frontend_safety", ROOT / "tools/lint_frontend_safety.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_outlier_bootstrap_is_small_and_loads_core_module() -> None:
    source = read("outlier-ui.js")
    assert len(source.splitlines()) < 40
    assert 'import("/outlier-core.js")' in source
    assert 'view") === "outlier"' in source


def test_outlier_modules_exist() -> None:
    public_legacy = {
        "outlier-shared.js",
        "outlier-core.js",
        "outlier-picks.js",
        "outlier-model-room.js",
        "outlier-admin.js",
    }
    assert public_legacy.issubset({path.name for path in PUBLIC.glob("outlier-*.js")})
    assert not (PUBLIC / "outlier-board.js").exists()
    assert not (PUBLIC / "outlier-detail.js").exists()
    assert (FRONTEND / "board" / "BoardTable.ts").exists()
    assert (FRONTEND / "board" / "BoardRow.ts").exists()
    assert (FRONTEND / "detail-rail" / "DetailRail.ts").exists()


def test_core_eager_primary_and_lazy_secondary_modules() -> None:
    source = read("outlier-core.js")
    assert 'outlier-board.js' not in source
    assert 'outlier-detail.js' not in source
    assert 'board: async () => viteBoardRedirect()' in source
    assert 'detail: async () => inertDetailModule()' in source
    assert 'picks: () => import("/outlier-picks.js")' in source
    assert '"model-room": () => import("/outlier-model-room.js")' in source
    assert 'admin: () => import("/outlier-admin.js")' in source
    assert 'await activateNav("Props")' in source
    assert 'className: "ob-sidebar"' in source
    assert 'className: "ob-right-rail"' in source


def test_board_module_is_vite_virtualized_and_rail_is_decoupled() -> None:
    board = read_frontend("board/BoardTable.ts")
    virtualized = read_frontend("board/virtualized.ts")
    rail = read_frontend("detail-rail/DetailRail.ts")
    main = read_frontend("main.ts")
    assert "createVirtualWindow" in board
    assert "scrollTop" in virtualized
    assert "rows.slice(0" not in virtualized
    assert "jsonFetch<PropDetailPayload>" in rail
    assert "detailRail.open" in main


def test_admin_module_is_quarantined_not_action_executor() -> None:
    source = read("outlier-admin.js")
    assert "not executable from the betting shell" in source
    assert "fetch(" not in source
    assert "jsonFetch" not in source


def test_frontend_safety_lint_passes_for_trust_critical_modules() -> None:
    linter = load_safety_linter()
    findings = linter.scan(ROOT, list(linter.DEFAULT_TARGETS))
    assert findings == []


def test_safety_lint_reports_markup_assignment(tmp_path: Path) -> None:
    public = tmp_path / "public"
    public.mkdir()
    sample = public / "outlier-bad.js"
    sample.write_text('const x = document.createElement("div");\nx.innerHTML = apiValue;\n', encoding="utf-8")
    linter = load_safety_linter()
    findings = linter.scan(tmp_path, ["public/outlier-*.js"])
    assert findings
    assert findings[0].kind == "unsafe_markup_assignment"


def test_phase8_visual_restores_classic_outlier_shell() -> None:
    main = read_frontend("main.ts")
    board = read_frontend("board/BoardTable.ts")
    css = (ROOT / "frontend" / "src" / "shared" / "styles" / "layout.css").read_text(encoding="utf-8")
    assert 'className: "outlier-app"' in main
    assert 'Baseball Edge' in main
    assert 'className: "ob-hero"' in main
    assert 'className: "ob-filter-grid"' in main
    assert 'ob-table' in board
    assert 'ob-shell-modular' not in main
    assert 'ob-shell-modular' not in css


def test_outlier_runtime_is_isolated_from_legacy_script_stack() -> None:
    index = read("index.html")
    legacy = read("legacy.html")
    assert 'data-runtime-ui' not in index
    assert 'legacyScripts' not in index
    assert '/assets/outlier-' in index
    assert '/app.js' not in index
    assert '/stage3-betting-ui.js' not in index
    assert '/trust-surface.js' not in index
    assert '/outlier-ui.js' not in index
    assert '/app.js' in legacy
    assert '/trust-surface.js' in legacy
    assert '/outlier-ui.js' not in legacy
