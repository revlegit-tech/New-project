from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def scan_playerboard(path: Path) -> dict[str, str | int]:
    run_label = next((part for part in path.parts if "-" in part and part[:4].isdigit()), "")
    date_counts: Counter[str] = Counter()
    market_counts: Counter[str] = Counter()
    total = 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        date_col = "date" if "date" in fields else None
        market_col = "market" if "market" in fields else None

        for row in reader:
            total += 1
            if date_col and row.get(date_col):
                date_counts[str(row.get(date_col))] += 1
            if market_col and row.get(market_col):
                market_counts[str(row.get(market_col))] += 1

    return {
        "run_label": run_label,
        "file": str(path),
        "rows": total,
        "top_dates": "; ".join(f"{key}:{value}" for key, value in date_counts.most_common(5)),
        "top_markets": "; ".join(f"{key}:{value}" for key, value in market_counts.most_common(12)),
        "has_batter_hr": market_counts.get("batter_home_runs", 0),
        "has_total_bases": market_counts.get("batter_total_bases", 0),
        "has_hits": market_counts.get("batter_hits", 0),
        "has_pitcher_k": market_counts.get("pitcher_strikeouts", 0),
        "has_pitcher_outs": market_counts.get("pitcher_outs", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan recovered artifact playerboard files by date and market.")
    parser.add_argument("--root", default="data/artifact_imports", help="Recovered artifact import root.")
    parser.add_argument("--season", default="2026", help="Season suffix used in playerboard_<season>.csv.")
    parser.add_argument("--out", default="data/health/artifact_playerboard_market_scan.csv", help="Manifest CSV output path.")
    args = parser.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    pattern = f"data/playerboard/playerboard_{args.season}.csv"
    files = sorted(root.rglob(pattern)) if root.exists() else []
    rows = [scan_playerboard(path) for path in files]

    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_label",
        "rows",
        "top_dates",
        "top_markets",
        "has_batter_hr",
        "has_total_bases",
        "has_hits",
        "has_pitcher_k",
        "has_pitcher_outs",
        "file",
    ]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if not root.exists():
        print(f"Artifact root not found; wrote empty manifest: {out}")
        return 0

    print(f"Scanned {len(files)} playerboard files")
    print(f"Manifest saved to: {out}")
    for row in rows:
        print(
            f"{row['run_label']}: rows={row['rows']} "
            f"hits={row['has_hits']} tb={row['has_total_bases']} "
            f"hr={row['has_batter_hr']} k={row['has_pitcher_k']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
