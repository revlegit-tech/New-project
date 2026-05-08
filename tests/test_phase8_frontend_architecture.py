from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


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
    expected = {
        "outlier-shared.js",
        "outlier-core.js",
        "outlier-board.js",
        "outlier-detail.js",
        "outlier-picks.js",
        "outlier-model-room.js",
        "outlier-admin.js",
    }
    assert expected.issubset({path.name for path in PUBLIC.glob("outlier-*.js")})


def test_core_eager_primary_and_lazy_secondary_modules() -> None:
    source = read("outlier-core.js")
    assert 'board: () => import("/outlier-board.js")' in source
    assert 'detail: () => import("/outlier-detail.js")' in source
    assert 'picks: () => import("/outlier-picks.js")' in source
    assert '"model-room": () => import("/outlier-model-room.js")' in source
    assert 'admin: () => import("/outlier-admin.js")' in source
    assert 'await activateNav("Props")' in source
    assert 'className: "ob-sidebar"' in source
    assert 'className: "ob-right-rail"' in source


def test_board_module_loads_detail_only_after_row_selection() -> None:
    source = read("outlier-board.js")
    assert 'import("/outlier-detail.js")' in source
    assert "host.onclick" in source
    assert "outlier:open-detail" in source


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
    core = read("outlier-core.js")
    board = read("outlier-board.js")
    css = read("outlier-ui.css")
    assert 'className: "outlier-app"' in core
    assert 'Baseball Edge' in core
    assert 'className: "ob-hero"' in board
    assert 'className: "ob-filter-shell"' in board
    assert 'className: "ob-table"' in board
    assert 'ob-shell-modular' not in core
    assert 'ob-shell-modular' not in css


def test_outlier_runtime_is_isolated_from_legacy_script_stack() -> None:
    index = read("index.html")
    assert 'data-runtime-ui' in index
    assert 'const outlier = params.get("view") === "outlier" || params.has("outlier")' in index
    assert 'const runtimeScripts = outlier ? ["/outlier-ui.js"] : legacyScripts' in index
    # Legacy scripts must be data in the conditional loader, not eager script tags that run behind Outlier.
    assert '<script src="/app.js"></script>' not in index
    assert '<script src="/stage3-betting-ui.js"></script>' not in index
    assert '<script src="/trust-surface.js"></script>' not in index
    assert '<script src="/outlier-ui.js"></script>' not in index
