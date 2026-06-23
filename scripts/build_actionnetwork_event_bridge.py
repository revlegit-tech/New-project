from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.actionnetwork_event_bridge_service import ActionNetworkEventBridgeService, read_csv
from mlb_app.services.mlb_truth_log_resolver import load_truth_logs


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source",
        "game_date",
        "snapshot_id",
        "event_id",
        "gamePk",
        "event_players",
        "local_players",
        "overlap",
        "event_share",
        "game_share",
        "confidence",
        "duplicate_best_gamePk",
        "bridge_status",
        "exclude_from_ml",
        "exclude_reason",
        "sample_overlap",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ActionNetwork event_id to MLB gamePk bridge.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--odds-path", default=None)
    parser.add_argument("--truth-dir", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    odds_path = Path(args.odds_path) if args.odds_path else Path("data/warehouse/normalized/odds") / f"actionnetwork_all_markets_{args.date}.csv"
    output = Path(args.output) if args.output else Path("data/warehouse/quality") / f"actionnetwork_event_game_bridge_{args.date}.csv"
    truth = load_truth_logs(args.season, truth_dir=args.truth_dir)
    rows = ActionNetworkEventBridgeService().build_rows(
        odds_rows=read_csv(odds_path),
        batter_rows=truth.batter_rows,
        pitcher_rows=truth.pitcher_rows,
        team_rows=truth.team_rows,
        snapshot_id=args.date,
    )
    write_csv(output, rows)
    print(f"bridge_csv={output}")
    print(f"rows={len(rows)}")
    print(f"truth_source_dir={truth.source_dir or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
