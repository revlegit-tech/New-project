#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.repositories.board_snapshot_repository import BoardSnapshotRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="List or activate SQLite-backed board snapshots.")
    parser.add_argument("--root", default=".", help="Application root used to resolve Settings paths.")
    parser.add_argument("--season", type=int, default=None, help="Optional season filter for --list.")
    parser.add_argument("--date", default="", help="Optional date filter for --list.")
    parser.add_argument("--list", action="store_true", help="List recent snapshots instead of activating one.")
    parser.add_argument("--activate", default="", help="Snapshot id to promote to active.")
    args = parser.parse_args()

    settings = Settings.from_env(Path(args.root).resolve())
    repository = BoardSnapshotRepository(settings)

    if args.list or not args.activate:
        records = repository.list_snapshots(season=args.season, date_label=args.date)
        print(json.dumps([record.__dict__ for record in records], indent=2, sort_keys=True))
        return

    record = repository.activate_snapshot(args.activate)
    print(json.dumps({"activated": record.__dict__}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
