from __future__ import annotations

"""Phase 20 v2 hotfix: rail selection restore + advanced modal space polish.

The Phase 20 polish made the game-context display cleaner, but two UX issues can
remain in local branches:

1. Clicking a row can open the advanced prop modal while the right rail still
   shows "Select a prop". We make row selection durable by storing the selected
   row on window and redispatching the rail event after the modal opens.
2. The advanced prop modal leaves usable space on wide screens and its percent
   helper displays decimal probabilities like 0.50495 as 0.5% instead of 50.5%.
"""

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def backup(path: Path) -> str:
    if not path.exists():
        return ""
    dest = path.with_name(f"{path.name}.phase20v2_backup_{STAMP}")
    shutil.copy2(path, dest)
    return str(dest)


def upsert_block(content: str, start: str, end: str, block: str) -> tuple[str, bool]:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{block.rstrip()}\n{end}"
    if pattern.search(content):
        updated = pattern.sub(replacement, content)
        return updated, updated != content
    if content and not content.endswith("\n"):
        content += "\n"
    return content + "\n" + replacement + "\n", True


def patch_outlier_board() -> dict[str, Any]:
    path = ROOT / "public" / "outlier-board.js"
    if not path.exists():
        return {"exists": False, "changed": False}
    original = read(path)
    updated = original

    # Store the selected row before any dynamic imports. This gives the rail a
    # fallback if the modal opens but the first dispatch is missed.
    target = "  if (!row) return;\n\n  try {"
    replacement = "  if (!row) return;\n  window.__OUTLIER_SELECTED_ROW__ = { row, index, selectedAt: Date.now() };\n  try { document.dispatchEvent(new CustomEvent(\"phase20:row-selected\", { detail: { row, index } })); } catch {}\n\n  try {"
    if target in updated and replacement not in updated:
        updated = updated.replace(target, replacement, 1)

    # Re-dispatch after the modal opens. The modal focus path can happen after
    # rail render on some browsers; this keeps the right rail populated.
    target2 = "    launcher.remove();\n  } catch (error) {"
    replacement2 = "    launcher.remove();\n    setTimeout(() => {\n      try { dispatch(\"outlier:open-detail\", { row, index, source: \"phase20v2-post-modal\" }); } catch {}\n      try { document.dispatchEvent(new CustomEvent(\"phase20:row-selected\", { detail: { row, index } })); } catch {}\n    }, 0);\n  } catch (error) {"
    if target2 in updated and replacement2 not in updated:
        updated = updated.replace(target2, replacement2, 1)

    changed = updated != original
    b = backup(path) if changed else ""
    if changed:
        write(path, updated)
    return {"exists": True, "changed": changed, "backup": b}


def patch_outlier_detail() -> dict[str, Any]:
    path = ROOT / "public" / "outlier-detail.js"
    if not path.exists():
        return {"exists": False, "changed": False}
    original = read(path)
    updated = original

    # Listen for the alternate durable selection event added in outlier-board.js.
    if 'listen("phase20:row-selected"' not in updated:
        needle = '''  listen("outlier:open-detail", (event) => {
    detailState.row = event.detail?.row || null;
    detailState.tab = "Matchup";
    renderDetail(detailState.row);
    dispatch("outlier:rail-open", {});
  });'''
        insert = needle + '''
  listen("phase20:row-selected", (event) => {
    detailState.row = event.detail?.row || window.__OUTLIER_SELECTED_ROW__?.row || null;
    detailState.tab = "Matchup";
    renderDetail(detailState.row);
    dispatch("outlier:rail-open", {});
  });'''
        if needle in updated:
            updated = updated.replace(needle, insert, 1)

    # If something calls renderDetail(null) while a recent selected row exists,
    # keep the rail useful instead of showing the empty state.
    needle2 = '''function renderDetail(row) {
  const host = document.getElementById("outlierDetailHost");
  if (!host) return;
  replaceChildren(host, [row ? detailPanel(row) : emptyPanel()]);
}'''
    repl2 = '''function renderDetail(row) {
  const host = document.getElementById("outlierDetailHost");
  if (!host) return;
  const fallback = window.__OUTLIER_SELECTED_ROW__?.row || null;
  const selected = row || fallback;
  replaceChildren(host, [selected ? detailPanel(selected) : emptyPanel()]);
}'''
    if needle2 in updated and repl2 not in updated:
        updated = updated.replace(needle2, repl2, 1)

    changed = updated != original
    b = backup(path) if changed else ""
    if changed:
        write(path, updated)
    return {"exists": True, "changed": changed, "backup": b}


def patch_prop_detail_js() -> dict[str, Any]:
    path = ROOT / "public" / "prop-detail.js"
    if not path.exists():
        return {"exists": False, "changed": False}
    original = read(path)
    updated = original

    old = '''  function pct(value) {
    const num = asNumber(value, NaN);
    if (!Number.isFinite(num)) return "Not available";
    return `${num.toFixed(Math.abs(num) >= 10 ? 0 : 1)}%`;
  }'''
    new = '''  function pct(value) {
    const num = asNumber(value, NaN);
    if (!Number.isFinite(num)) return "Not available";
    const pctValue = Math.abs(num) <= 1 ? num * 100 : num;
    return `${pctValue.toFixed(Math.abs(pctValue) >= 10 ? 0 : 1)}%`;
  }'''
    if old in updated:
        updated = updated.replace(old, new, 1)

    changed = updated != original
    b = backup(path) if changed else ""
    if changed:
        write(path, updated)
    return {"exists": True, "changed": changed, "backup": b}


def patch_css() -> dict[str, Any]:
    css_candidates = [ROOT / "public" / "styles.css", ROOT / "public" / "outlier-ui.css"]
    results: list[dict[str, Any]] = []
    block = r'''
/* Phase 20 v2: use more of the modal viewport and reduce dead space. */
.outlier-prop-detail-v2 .prop-detail-dialog {
  width: min(1240px, calc(100vw - 64px));
  max-width: min(1240px, calc(100vw - 64px));
  max-height: calc(100vh - 36px);
}

.outlier-prop-detail-v2 .prop-detail-grid-v2 {
  grid-template-columns: minmax(520px, 1.15fr) minmax(390px, 0.85fr);
  align-items: start;
}

.outlier-prop-detail-v2 .prop-detail-overview-panel,
.outlier-prop-detail-v2 .prop-detail-hit-panel {
  min-width: 0;
}

.outlier-prop-detail-v2 .prop-detail-context-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.outlier-prop-detail-v2 .prop-detail-metric-row.compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.outlier-prop-detail-v2 .prop-detail-game-chart {
  min-height: 150px;
}

@media (max-width: 980px) {
  .outlier-prop-detail-v2 .prop-detail-dialog {
    width: calc(100vw - 24px);
    max-width: calc(100vw - 24px);
  }
  .outlier-prop-detail-v2 .prop-detail-grid-v2,
  .outlier-prop-detail-v2 .prop-detail-context-grid {
    grid-template-columns: 1fr;
  }
}
'''
    for path in css_candidates:
        if not path.exists():
            results.append({"path": str(path), "exists": False, "changed": False})
            continue
        original = read(path)
        updated, changed = upsert_block(original, "/* PHASE20_V2_MODAL_SPACE_START */", "/* PHASE20_V2_MODAL_SPACE_END */", block)
        b = backup(path) if changed else ""
        if changed:
            write(path, updated)
        results.append({"path": str(path), "exists": True, "changed": changed, "backup": b})
    return {"targets": results, "changed": any(item.get("changed") for item in results)}


def main() -> None:
    result = {
        "outlierBoard": patch_outlier_board(),
        "outlierDetail": patch_outlier_detail(),
        "propDetailJs": patch_prop_detail_js(),
        "css": patch_css(),
    }
    print(result)


if __name__ == "__main__":
    main()
