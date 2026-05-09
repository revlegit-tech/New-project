#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

LEGACY_OUTLIER_SOURCES = (
    "/outlier-board.js",
    "/outlier-detail.js",
    "/src/outlier/main.ts",
)


def main() -> int:
    root = Path.cwd()
    index = root / "public" / "index.html"
    assets = root / "public" / "assets"
    if not index.exists():
        print("public/index.html is missing; run npm run build first.", file=sys.stderr)
        return 2
    html = index.read_text(encoding="utf-8", errors="replace")
    script_match = re.search(r'<script\b[^>]*\bsrc=["\'](/assets/outlier-[A-Za-z0-9_-]+\.js)["\']', html)
    if not script_match:
        print("public/index.html does not reference a fingerprinted /assets/outlier-*.js bundle.", file=sys.stderr)
        return 2
    script = script_match.group(1)
    script_path = root / "public" / script.lstrip("/")
    if not script_path.exists():
        print(f"fingerprinted bundle referenced by index.html is missing: {script}", file=sys.stderr)
        return 2
    failures = [needle for needle in LEGACY_OUTLIER_SOURCES if needle in html]
    if failures:
        print(f"public/index.html still references raw frontend/legacy source: {', '.join(failures)}", file=sys.stderr)
        return 2
    if not assets.exists():
        print("public/assets/ is missing; Vite build output was not produced.", file=sys.stderr)
        return 2
    bundle_text = script_path.read_text(encoding="utf-8", errors="replace")
    embedded = [needle for needle in LEGACY_OUTLIER_SOURCES if needle in bundle_text]
    if embedded:
        print(f"fingerprinted bundle still dynamically imports raw legacy outlier source: {', '.join(embedded)}", file=sys.stderr)
        return 2
    print(f"Vite asset validation passed: {script} is the production Outlier bundle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
