from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.atomic_file_service import atomic_write_json
from tools.validate_backup_files import iter_backup_files


def build_summary(*, date_label: str, execute: bool = False, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    season = int(date_label[:4])
    files = [
        root / "data" / "warehouse" / "season_logs" / f"batter_game_logs_{season}.csv",
        root / "data" / "warehouse" / "season_logs" / f"pitcher_game_logs_{season}.csv",
        root / "data" / "warehouse" / "season_logs" / f"team_game_logs_{season}.csv",
        root / "data" / "backtests" / f"playerboard_backtest_{season}.csv",
        root / "data" / "ml" / f"playerboard_training_{season}.csv",
    ]
    warnings: list[str] = []
    file_status: dict[str, Any] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        exists = path.exists()
        file_status[rel] = {"exists": exists, "size": path.stat().st_size if exists else 0}
        if not exists:
            warnings.append(f"Optional repair artifact is missing: {rel}")

    backup_files = [path.as_posix() for path in iter_backup_files(root)]
    if backup_files:
        warnings.append("Source-tree backup/temp files were detected.")

    status = "ok" if not backup_files else "failed"
    return {
        "schemaVersion": "weekly-repair.v1",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "date": date_label,
        "season": season,
        "workflow": "weekly-data-repair",
        "status": status,
        "ok": status != "failed",
        "dryRun": not execute,
        "mode": "execute" if execute else "dry-run",
        "files": file_status,
        "warnings": warnings,
        "recommendations": [
            "Scheduled weekly repair runs in dry-run mode by default.",
            "Use workflow_dispatch execute=true only after reviewing the summary.",
        ],
        "backupFiles": backup_files,
        "modelTrainingTriggered": False,
        "externalApiCallsMade": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe weekly data repair contract.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    summary = build_summary(date_label=args.date, execute=args.execute, root=Path(args.root))
    health_dir = Path(args.root) / "data" / "health"
    atomic_write_json(health_dir / f"weekly_repair_{args.date}.json", summary)
    atomic_write_json(health_dir / "latest_weekly_repair.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
