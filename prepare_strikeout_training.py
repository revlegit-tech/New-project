from __future__ import annotations

"""Prepare clean pitcher-strikeout training data after game-odds merging.

This fixes the common training error:
    ValueError: Training row needs an over/result column or actual stat plus line.

It does that by:
- reading historical_props_with_game_odds.csv or historical_props.csv
- keeping only pitcher_strikeouts
- keeping only Over rows by default
- dropping rows with blank line and blank actual/over
- normalizing columns the ML model expects
- keeping game-odds features when present
- writing data/training/pitcher_strikeouts_training.csv

Usage:
    python prepare_strikeout_training.py

Optional:
    python prepare_strikeout_training.py --input data/training/historical_props_with_game_odds.csv --out data/training/pitcher_strikeouts_training.csv
"""

import argparse
import csv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

DEFAULT_INPUTS = [
    DATA_DIR / "training" / "historical_props_with_game_odds.csv",
    DATA_DIR / "training" / "historical_props.csv",
]

DEFAULT_OUTPUT = DATA_DIR / "training" / "pitcher_strikeouts_training.csv"

BASE_COLUMNS = [
    "date",
    "player",
    "market",
    "line",
    "american_odds",
    "actual",
    "over",
    "team",
    "opponent",
    "book",
    "side",
    "game",
    "event_id",
]

GAME_ODDS_COLUMNS = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "favorite_status",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
]

# These are model feature columns from ml_prop_model.py. They can be blank,
# but keeping them in the CSV makes future enrichment easier.
MODEL_FEATURE_COLUMNS = [
    "recent_games",
    "recent_rate",
    "season_rate",
    "rolling_avg_5",
    "rolling_avg_10",
    "rolling_avg_15",
    "rolling_total_bases_10",
    "rolling_hr_rate_15",
    "rolling_k_rate_10",
    "opponent_rate",
    "pitcher_k_rate",
    "pitcher_walk_rate",
    "pitcher_hr_rate",
    "team_k_rate",
    "team_walk_rate",
    "batter_k_rate",
    "batter_walk_rate",
    "barrel_rate",
    "hard_hit_rate",
    "xwoba",
    "xba",
    "xslg",
    "park_factor",
    "hit_factor",
    "hr_factor",
    "k_factor",
    "temperature",
    "wind_mph",
    "throws",
    "bats",
    "venue",
    "roof",
]


def first_existing_input() -> Path:
    for path in DEFAULT_INPUTS:
        if not path.exists():
            continue
        if path.name == "historical_props_with_game_odds.csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
            if not header or not all(field in header for field in ("date", "team", "opponent")):
                continue
        return path
    raise FileNotFoundError(
        "Could not find data/training/historical_props_with_game_odds.csv "
        "or data/training/historical_props.csv"
    )


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any) -> float | None:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_truthy_over(value: Any) -> str:
    text = clean(value).lower()
    if text in {"1", "true", "yes", "y", "over", "hit", "won", "win"}:
        return "1"
    if text in {"0", "false", "no", "n", "under", "miss", "lost", "loss"}:
        return "0"
    return ""


def normalize_row(row: dict[str, Any]) -> dict[str, str] | None:
    market = clean(row.get("market"))
    if market != "pitcher_strikeouts":
        return None

    side = clean(row.get("side"))
    if side and side.lower() != "over":
        return None

    line = clean(row.get("line"))
    actual = clean(row.get("actual"))
    over = is_truthy_over(row.get("over"))

    # If over is blank but actual+line exist, calculate it.
    if not over:
        actual_float = to_float(actual)
        line_float = to_float(line)
        if actual_float is not None and line_float is not None:
            over = "1" if actual_float > line_float else "0"

    # Drop rows that the ML model cannot use.
    if not line or (not actual and not over):
        return None

    out: dict[str, str] = {}
    for column in BASE_COLUMNS + GAME_ODDS_COLUMNS + MODEL_FEATURE_COLUMNS:
        out[column] = clean(row.get(column))

    out["market"] = "pitcher_strikeouts"
    out["side"] = "Over"
    out["line"] = line
    out["actual"] = actual
    out["over"] = over

    # Map game-odds context into model feature names where useful.
    if not out.get("opponent_rate") and out.get("opponent_implied_runs_proxy"):
        out["opponent_rate"] = out["opponent_implied_runs_proxy"]
    if not out.get("park_factor"):
        out["park_factor"] = "1.0"

    return out


def prepare(input_path: Path, output_path: Path) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    clean_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()

    for row in rows:
        normalized = normalize_row(row)
        if not normalized:
            continue

        key = (
            normalized.get("date", ""),
            normalized.get("player", ""),
            normalized.get("line", ""),
            normalized.get("american_odds", ""),
            normalized.get("book", ""),
            normalized.get("game", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        clean_rows.append(normalized)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = BASE_COLUMNS + GAME_ODDS_COLUMNS + MODEL_FEATURE_COLUMNS

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in clean_rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})

    teams = sorted({row.get("team", "") for row in clean_rows if row.get("team", "")})
    opponents = sorted({row.get("opponent", "") for row in clean_rows if row.get("opponent", "")})

    return {
        "input": str(input_path),
        "output": str(output_path),
        "inputRows": len(rows),
        "trainingRows": len(clean_rows),
        "teamsCovered": len(teams),
        "opponentsCovered": len(opponents),
        "teams": ", ".join(teams),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare clean pitcher strikeout ML training data.")
    parser.add_argument("--input", default="", help="Input CSV. Defaults to enriched historical props if present.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output clean training CSV.")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else first_existing_input()
    summary = prepare(input_path, Path(args.out))

    for key, value in summary.items():
        print(f"{key}: {value}")

    if summary["trainingRows"] < 25:
        print("WARNING: Fewer than 25 clean rows. Collect/grade more pitcher strikeout props before training.")


if __name__ == "__main__":
    main()
