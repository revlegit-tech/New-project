from __future__ import annotations

"""Hook Phase 19 observed line movement into season_auto_collector.py."""

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "season_auto_collector.py"
MARKER = "PHASE19_LINE_MOVEMENT_HOOK"

HOOK = """\n        # PHASE19_LINE_MOVEMENT_HOOK_START\n        try:\n            from tools.phase19_line_movement import run_phase19\n\n            summary["phase19LineMovement"] = run_phase19(\n                date_label=date_label,\n                season=int(date_label[:4]),\n                source="season_auto_collector",\n                patch_playerboard=False,\n            )\n        except Exception as line_movement_error:\n            summary["phase19LineMovement"] = {\n                "error": str(line_movement_error),\n                "status": "warning",\n            }\n        # PHASE19_LINE_MOVEMENT_HOOK_END\n"""


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print({"status": "noop", "reason": "Phase 19 hook already present", "path": str(TARGET)})
        return
    anchor = '        summary["cloudExport"] = export_compact_cloud_data(date_label, summary)'
    if anchor not in text:
        raise RuntimeError("Could not find cloudExport anchor in season_auto_collector.py")
    backup = TARGET.with_suffix(TARGET.suffix + f".phase19_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    shutil.copy2(TARGET, backup)
    TARGET.write_text(text.replace(anchor, HOOK + "\n" + anchor), encoding="utf-8")
    print({"status": "ok", "changed": True, "path": str(TARGET), "backup": str(backup)})


if __name__ == "__main__":
    main()
