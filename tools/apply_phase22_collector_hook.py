from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "season_auto_collector.py"
MARKER = "# PHASE22_ODDSPAPI_CLV_HOOK_START"
ANCHOR = "# PHASE19_LINE_MOVEMENT_HOOK_END"
HOOK = '''\n\n        # PHASE22_ODDSPAPI_CLV_HOOK_START\n        try:\n            from tools.phase22_oddspapi_clv import run_phase22\n\n            summary["phase22OddsPapiClv"] = run_phase22(\n                date_label=date_label,\n                season=int(date_label[:4]),\n                apply=True,\n            )\n        except Exception as oddspapi_clv_error:\n            summary["phase22OddsPapiClv"] = {\n                "error": str(oddspapi_clv_error),\n                "status": "warning",\n            }\n        # PHASE22_ODDSPAPI_CLV_HOOK_END\n'''


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print({"status": "ok", "changed": False, "reason": "Phase 22 hook already present", "path": str(TARGET)})
        return
    if ANCHOR not in text:
        raise RuntimeError(f"Could not find anchor {ANCHOR!r} in {TARGET}")
    backup = TARGET.with_suffix(TARGET.suffix + f".phase22_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    backup.write_text(text, encoding="utf-8")
    text = text.replace(ANCHOR, ANCHOR + HOOK, 1)
    TARGET.write_text(text, encoding="utf-8")
    print({"status": "ok", "changed": True, "path": str(TARGET), "backup": str(backup)})


if __name__ == "__main__":
    main()
