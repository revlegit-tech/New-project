from __future__ import annotations

"""Phase 23 hook installer.

Adds the Phase 23 daily refresh QA report to tools/run_daily_refresh.py after the
existing Phase 21 freshness report step.
"""

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "run_daily_refresh.py"

START = "    # PHASE23_DAILY_REFRESH_QA_HOOK_START\n"
END = "    # PHASE23_DAILY_REFRESH_QA_HOOK_END\n"
ANCHOR = "    if result.get(\"collector\", {}).get(\"status\") == \"warning\":\n"

HOOK = f"""
{START}    phase23_cmd = [
        sys.executable,
        str(ROOT / "tools" / "phase23_daily_refresh_qa.py"),
        "--date",
        args.date,
        "--season",
        str(args.season),
        "--write",
    ]
    result["phase23QaCommand"] = run_command(phase23_cmd, timeout=180)
    phase23_path = AUDIT_DIR / f"phase23_daily_refresh_qa_{{args.date}}.json"
    if phase23_path.exists():
        try:
            result["phase23Qa"] = json.loads(phase23_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result["phase23Qa"] = {{"status": "warning", "error": "Could not parse Phase 23 QA JSON."}}

{END}"""


def apply() -> dict[str, object]:
    if not TARGET.exists():
        raise FileNotFoundError(f"Target not found: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    if START in text and END in text:
        return {"status": "ok", "changed": False, "path": str(TARGET), "reason": "hook already present"}

    if ANCHOR not in text:
        raise RuntimeError("Could not find run_daily_refresh status-evaluation anchor.")

    backup = TARGET.with_suffix(TARGET.suffix + f".phase23_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    backup.write_text(text, encoding="utf-8")

    text = text.replace(ANCHOR, HOOK + ANCHOR, 1)

    phase23_status_check = """    if result.get(\"phase23QaCommand\", {}).get(\"status\") == \"warning\":\n        result[\"status\"] = \"warning\"\n    if isinstance(result.get(\"phase23Qa\"), dict) and result[\"phase23Qa\"].get(\"status\") == \"warning\":\n        result[\"status\"] = \"warning\"\n"""
    freshness_check = """    if isinstance(result.get(\"freshness\"), dict) and result[\"freshness\"].get(\"status\") == \"warning\":\n        result[\"status\"] = \"warning\"\n"""
    if phase23_status_check.strip() not in text:
        text = text.replace(freshness_check, freshness_check + phase23_status_check, 1)

    TARGET.write_text(text, encoding="utf-8")
    return {
        "status": "ok",
        "changed": True,
        "path": str(TARGET),
        "backup": str(backup),
        "reason": "Inserted Phase 23 daily refresh QA after the Phase 21 freshness report.",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(apply(), indent=2))
