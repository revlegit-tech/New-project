from __future__ import annotations

"""Allow season_auto_collector.py to accept --run-type scheduled.

The canonical scheduled entrypoint is tools/run_daily_refresh.py. This patch only
adds a compatibility alias so operator muscle memory does not fail with an
argparse error. The alias maps scheduled -> morning inside season_auto_collector.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "season_auto_collector.py"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    original = text

    text = text.replace(
        'choices=["morning", "midday", "midnight", "manual", "grading"]',
        'choices=["scheduled", "morning", "midday", "midnight", "manual", "grading"]',
    )

    old = '''    if args.command == "snapshot":\n        date_label = resolve_date(args.date or None, args.date_offset)\n        print(json.dumps(\n            snapshot(date_label, args.run_type, include_savant=args.include_savant),\n            indent=2,\n            ensure_ascii=False,\n        ))\n'''
    new = '''    if args.command == "snapshot":\n        date_label = resolve_date(args.date or None, args.date_offset)\n        run_type = "morning" if args.run_type == "scheduled" else args.run_type\n        print(json.dumps(\n            snapshot(date_label, run_type, include_savant=args.include_savant),\n            indent=2,\n            ensure_ascii=False,\n        ))\n'''
    if old in text:
        text = text.replace(old, new)

    changed = text != original
    if changed:
        backup = TARGET.with_suffix(TARGET.suffix + ".phase21_backup")
        backup.write_text(original, encoding="utf-8")
        TARGET.write_text(text, encoding="utf-8")
    print({"status": "ok", "changed": changed, "path": str(TARGET)})


if __name__ == "__main__":
    main()
