from __future__ import annotations

"""Phase 22 v4 hook installer.

Adds the Phase 22 v3 fixture-metadata fallback to season_auto_collector.py
immediately after the existing Phase 22 OddsPapi CLV hook.

The hook is metadata-only. It does not fabricate opening lines, CLV, moneyline
movement, totals, or implied runs. Phase 19 remains the movement source unless
true CLV becomes available.
"""

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "season_auto_collector.py"

START = "        # PHASE22_V3_FIXTURE_METADATA_FALLBACK_HOOK_START\n"
END = "        # PHASE22_V3_FIXTURE_METADATA_FALLBACK_HOOK_END\n"
ANCHOR = "        # PHASE22_ODDSPAPI_CLV_HOOK_END\n"

HOOK = f"""\n{START}        try:\n            if os.environ.get(\"PHASE22_SKIP_FIXTURE_METADATA_FALLBACK\", \"\").strip().lower() in {{\"1\", \"true\", \"yes\"}}:\n                summary[\"phase22FixtureMetadataFallback\"] = {{\n                    \"status\": \"skipped\",\n                    \"reason\": \"PHASE22_SKIP_FIXTURE_METADATA_FALLBACK enabled\",\n                }}\n            else:\n                from tools.phase22_v3_fixture_metadata_fallback import apply_fixture_metadata\n\n                summary[\"phase22FixtureMetadataFallback\"] = apply_fixture_metadata(\n                    date=date_label,\n                    season=int(date_label[:4]),\n                    dry_run=False,\n                )\n        except FileNotFoundError as fixture_metadata_missing:\n            summary[\"phase22FixtureMetadataFallback\"] = {{\n                \"status\": \"skipped\",\n                \"reason\": str(fixture_metadata_missing),\n            }}\n        except Exception as fixture_metadata_error:\n            summary[\"phase22FixtureMetadataFallback\"] = {{\n                \"status\": \"warning\",\n                \"error\": str(fixture_metadata_error),\n            }}\n{END}"""


def apply() -> dict[str, object]:
    if not TARGET.exists():
        raise FileNotFoundError(f"Target not found: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    if START in text and END in text:
        return {"status": "ok", "changed": False, "path": str(TARGET), "reason": "hook already present"}

    if ANCHOR not in text:
        raise RuntimeError("Could not find Phase 22 OddsPapi CLV hook anchor in season_auto_collector.py")

    backup = TARGET.with_suffix(TARGET.suffix + f".phase22v4_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    backup.write_text(text, encoding="utf-8")

    text = text.replace(ANCHOR, ANCHOR + HOOK, 1)
    TARGET.write_text(text, encoding="utf-8")

    return {
        "status": "ok",
        "changed": True,
        "path": str(TARGET),
        "backup": str(backup),
        "reason": "Inserted Phase 22 v3 fixture metadata fallback after existing Phase 22 CLV hook.",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(apply(), indent=2))
