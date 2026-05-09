#!/usr/bin/env python3
"""Migrate legacy user-state JSON files into the SQLite WAL state database.

This tool is idempotent: it imports bankroll settings only when the singleton
row is missing and imports picks only when the picks table is empty. Services do
this migration automatically on first use, but the CLI gives operators an
explicit preflight path before deploying Sprint 3.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.repositories.bankroll_repository import BankrollRepository
from mlb_app.repositories.picks_repository import PicksRepository
from mlb_app.schemas.picks import Pick


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate user picks and bankroll settings from JSON to SQLite.")
    parser.add_argument("--root", type=Path, default=None, help="Project root. Defaults to MLB_APP_ROOT or current directory.")
    parser.add_argument("--db-path", type=Path, default=None, help="Override the SQLite state database path.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be imported without mutating SQLite.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(args.root)
    if args.db_path is not None:
        settings = replace(settings, db_path=args.db_path.resolve())

    bankroll_repo = BankrollRepository(settings)
    picks_repo = PicksRepository(settings)

    bankroll_payload = _read_json(settings.data_dir / "user" / "bankroll_settings.json")
    picks_payload = _read_json(settings.data_dir / "user" / "my_picks.json")
    legacy_picks = _payload_picks(picks_payload)

    actions: list[str] = []
    if not bankroll_repo.has_settings() and isinstance(bankroll_payload.get("settings"), dict):
        actions.append("import bankroll settings")
        if not args.dry_run:
            bankroll_repo.save_payload(bankroll_payload["settings"])

    if picks_repo.count() == 0 and legacy_picks:
        actions.append(f"import {len(legacy_picks)} picks")
        if not args.dry_run:
            picks_repo.replace_all([Pick.from_api(row).to_api() for row in legacy_picks])

    result = {
        "status": "ok",
        "dryRun": args.dry_run,
        "dbPath": str(settings.state_db_path),
        "actions": actions,
        "picksInDatabase": picks_repo.count(),
        "bankrollInDatabase": bankroll_repo.has_settings(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_picks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("picks", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
