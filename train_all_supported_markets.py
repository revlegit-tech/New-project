from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_MARKETS = [
    "batter_hits",
    "batter_home_runs",
    "batter_total_bases",
    "batter_rbis",
    "batter_stolen_bases",
    "team_total_runs",
    "team_first_to_score",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]

MIN_TRAINING_ROWS = 25


def rebuild_historical_props(season: int) -> tuple[Path, dict[str, Any]]:
    src = Path(f"data/backtests/playerboard_backtest_{season}.csv")
    out = Path("data/training/historical_props.csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "source": str(src),
        "output": str(out),
        "sourceExists": src.exists(),
        "rows": 0,
        "markets": {},
        "overCounts": {},
    }

    if not src.exists():
        summary["error"] = f"Backtest file not found: {src}"
        return out, summary

    df = pd.read_csv(src)

    if "result" not in df.columns:
        summary["error"] = f"{src} is missing required column: result"
        return out, summary

    df = df[df["result"].isin(["win", "loss"])].copy()

    if "americanOdds" in df.columns:
        df["american_odds"] = df["americanOdds"]

    if "actualStat" in df.columns:
        df["actual"] = df["actualStat"]

    df["over"] = df["result"].map({"win": 1, "loss": 0})

    if "sportsbookImpliedPercent" in df.columns:
        df["book_implied_percent"] = df["sportsbookImpliedPercent"]
        df["book_implied_probability"] = (
            pd.to_numeric(df["sportsbookImpliedPercent"], errors="coerce") / 100.0
        )

    if "finalProbabilityPercent" in df.columns:
        df["model_probability_percent"] = df["finalProbabilityPercent"]

    if "push" not in df.columns:
        df["push"] = 0

    df.to_csv(out, index=False)

    summary["rows"] = int(len(df))
    summary["markets"] = {
        str(k): int(v) for k, v in df["market"].value_counts(dropna=False).to_dict().items()
    }
    summary["overCounts"] = {
        str(k): int(v) for k, v in df["over"].value_counts(dropna=False).to_dict().items()
    }

    return out, summary


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print("Command:", " ".join(cmd))
    completed = subprocess.run(cmd, text=True, capture_output=True)

    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)

    return completed


def inspect_training_file(path: Path) -> tuple[int, dict[str, int]]:
    if not path.exists():
        return 0, {}

    df = pd.read_csv(path)
    rows = int(len(df))

    class_counts: dict[str, int] = {}
    if "over" in df.columns:
        class_counts = {
            str(k): int(v) for k, v in df["over"].value_counts(dropna=False).to_dict().items()
        }

    return rows, class_counts


def train_market(market: str, historical_path: Path) -> dict[str, Any]:
    output_path = Path("data/training") / f"{market}_training.csv"

    print("\n" + "=" * 100)
    print("Preparing market:", market)

    prepare_cmd = [
        sys.executable,
        "prepare_market_training.py",
        "--market",
        market,
        "--input",
        str(historical_path),
        "--out",
        str(output_path),
    ]

    prepare_result = run_command(prepare_cmd)
    rows, class_counts = inspect_training_file(output_path)

    result: dict[str, Any] = {
        "market": market,
        "prepareReturnCode": int(prepare_result.returncode),
        "trainReturnCode": None,
        "success": False,
        "trained": False,
        "skipped": False,
        "skipReason": "",
        "trainingFile": str(output_path),
        "trainingFileExists": output_path.exists(),
        "rows": rows,
        "classCounts": class_counts,
    }

    if prepare_result.returncode != 0:
        result["skipped"] = True
        result["skipReason"] = "prepare_market_training.py failed before training."
        return result

    if rows < MIN_TRAINING_ROWS:
        result["skipped"] = True
        result["skipReason"] = f"Only {rows} rows. Need at least {MIN_TRAINING_ROWS} rows before training."
        print(f"Skipping {market}: {result['skipReason']}")
        return result

    if len(class_counts) < 2:
        result["skipped"] = True
        result["skipReason"] = "Only one outcome class available. Need both over=0 and over=1."
        print(f"Skipping {market}: {result['skipReason']}")
        return result

    print("\nTraining market:", market)

    train_cmd = [
        sys.executable,
        "ml_prop_model.py",
        "train",
        str(output_path),
        "--market",
        market,
    ]

    train_result = run_command(train_cmd)
    result["trainReturnCode"] = int(train_result.returncode)
    result["success"] = train_result.returncode == 0
    result["trained"] = train_result.returncode == 0

    if train_result.returncode != 0:
        result["skipReason"] = "ml_prop_model.py failed during training."

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild and train all currently supported prop markets.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any trainable market fails.")
    args = parser.parse_args()

    summary: dict[str, Any] = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "season": args.season,
        "minimumTrainingRows": MIN_TRAINING_ROWS,
        "supportedMarkets": SUPPORTED_MARKETS,
        "historical": {},
        "markets": {},
        "success": True,
        "warnings": [],
    }

    historical_path, historical_summary = rebuild_historical_props(args.season)
    summary["historical"] = historical_summary

    if historical_summary.get("error"):
        summary["success"] = False
        summary["warnings"].append(historical_summary["error"])
    else:
        for market in SUPPORTED_MARKETS:
            result = train_market(market, historical_path)
            summary["markets"][market] = result

            if result.get("skipped"):
                summary["warnings"].append(f"{market} skipped: {result.get('skipReason')}")
            elif not result.get("success"):
                summary["success"] = False
                summary["warnings"].append(f"{market} failed during training.")

    out_dir = Path("data/training")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"train_all_supported_markets_summary_{args.season}.json"
    latest_path = out_dir / "latest_train_all_supported_markets_summary.json"

    text = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    latest_path.write_text(text + "\n", encoding="utf-8")

    print("\n" + "=" * 100)
    print(text)

    if args.strict and not summary["success"]:
        raise SystemExit(1)

    raise SystemExit(0)


if __name__ == "__main__":
    main()
