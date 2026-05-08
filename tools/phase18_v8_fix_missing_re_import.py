from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT / "mlb_app" / "services" / "edge_board_service.py"


def main() -> None:
    if not EDGE.exists():
        raise SystemExit(f"missing file: {EDGE}")

    text = EDGE.read_text(encoding="utf-8")
    changed = False

    # Add the stdlib regex import required by Phase 18 v7 helpers.
    if "import re" not in text.split("\n")[:80]:
        backup = EDGE.with_suffix(EDGE.suffix + f".phase18v8_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        backup.write_text(text, encoding="utf-8")

        lines = text.splitlines()
        insert_at = 0
        # Keep from __future__ first, then stdlib imports.
        for idx, line in enumerate(lines):
            if line.startswith("from __future__ import"):
                insert_at = idx + 1
                break
        if insert_at == 0:
            # Otherwise insert before first non-comment/non-blank import block.
            insert_at = 0
        lines.insert(insert_at, "import re")
        text = "\n".join(lines) + "\n"
        EDGE.write_text(text, encoding="utf-8")
        changed = True
        backup_path = str(backup)
    else:
        backup_path = ""

    print({
        "status": "ok",
        "changed": changed,
        "path": str(EDGE),
        "backup": backup_path,
        "reason": "Phase 18 v7 context join helpers call re.sub, so edge_board_service.py must import re.",
    })


if __name__ == "__main__":
    main()
