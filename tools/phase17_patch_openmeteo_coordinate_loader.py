"""Patch Phase 17 API bridge to prefer the canonical MLB venue coordinate CSV.

This script is intentionally conservative. It only edits fetch_phase17_context_from_apis.py
when it can find the known loader shape from the Phase 17 bridge. If the loader already
references mlb_venue_coordinates.csv, it does nothing.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "fetch_phase17_context_from_apis.py"

PREFERRED_SNIPPET = """\nCOORDINATE_REFERENCE_CANDIDATES = [\n    ROOT / "data" / "reference" / "mlb_venue_coordinates.csv",\n    ROOT / "data" / "reference" / "venue_coordinates.csv",\n    ROOT / "data" / "reference" / "stadium_coordinates.csv",\n]\n"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch the Phase 17 weather coordinate loader.")
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    path = args.target
    if not path.exists():
        print({"status": "skipped", "reason": f"missing target {path}"})
        return

    text = path.read_text(encoding="utf-8")
    if "mlb_venue_coordinates.csv" in text:
        print({"status": "ok", "changed": False, "reason": "loader already references canonical coordinate CSV"})
        return

    changed = False
    replacement = None
    if "venue_coordinates.csv" in text or "stadium_coordinates.csv" in text:
        replacement = re.sub(
            r"(ROOT\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[1\].*?\n)",
            r"\1" + PREFERRED_SNIPPET,
            text,
            count=1,
            flags=re.DOTALL,
        )
        changed = replacement != text

    if not changed:
        print({"status": "warning", "changed": False, "reason": "could not safely patch loader; coordinate files were still added"})
        return

    if args.write:
        path.write_text(replacement, encoding="utf-8")
    print({"status": "ok", "changed": True, "written": bool(args.write), "target": str(path)})


if __name__ == "__main__":
    main()
