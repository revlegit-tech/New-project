from __future__ import annotations

"""Add observed line movement fields to the Outlier right-rail Game Context card."""

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "public" / "outlier-detail.js"


def main() -> None:
    if not TARGET.exists():
        print({"status": "skipped", "reason": "public/outlier-detail.js missing"})
        return
    text = TARGET.read_text(encoding="utf-8")
    changed = False
    backup = ""

    metric_anchor = '        ["ML IP", percent(row.moneylineImpliedProbability ?? row.moneyline_implied_probability)],\n'
    metric_insert = metric_anchor + (
        '        ["Open ML", formatOdds(row.openTeamMoneyline ?? row.open_team_moneyline)],\n'
        '        ["ML Move", lineMove(row.moneylineMove ?? row.moneyline_move)],\n'
        '        ["Open Total", text(row.openGameTotal ?? row.open_game_total, "Missing")],\n'
        '        ["Total Move", lineMove(row.totalMove ?? row.total_move)],\n'
    )
    if metric_anchor in text and '"ML Move", lineMove' not in text:
        text = text.replace(metric_anchor, metric_insert)
        changed = True

    helper = """\nfunction lineMove(value) {\n  const parsed = number(value, NaN);\n  if (!Number.isFinite(parsed)) return "Missing";\n  if (parsed > 0) return `+${parsed}`;\n  return `${parsed}`;\n}\n"""
    if "function lineMove(" not in text:
        text = text.replace("function booksCard(row) {", helper + "\nfunction booksCard(row) {")
        changed = True

    if changed:
        backup_path = TARGET.with_suffix(TARGET.suffix + f".phase19_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        shutil.copy2(TARGET, backup_path)
        backup = str(backup_path)
        TARGET.write_text(text, encoding="utf-8")
    print({"status": "ok", "changed": changed, "path": str(TARGET), "backup": backup})


if __name__ == "__main__":
    main()
