from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
ODDSPAPI_DIR = ROOT / "data" / "cache" / "oddspapi"
ML_DIR = ROOT / "data" / "ml"

SUPPORTED_MARKETS = {
    "moneyline",
    "moneyline_first_five",
    "run_line",
    "run_line_first_five",
    "run_line_first_inning",
    "game_total_runs",
    "first_five_total_runs",
    "first_inning_total_runs",
    "team_total_runs",
    "team_first_to_score",
}

MARKET_FAMILY = {
    "moneyline": "moneyline",
    "moneyline_first_five": "moneyline",
    "run_line": "spread",
    "run_line_first_five": "spread",
    "run_line_first_inning": "spread",
    "game_total_runs": "total",
    "first_five_total_runs": "total",
    "first_inning_total_runs": "total",
    "team_total_runs": "team_total",
    "team_first_to_score": "first_score",
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace("+", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def american_to_implied(odds: Any) -> float:
    value = to_float(odds, 0.0)
    if value == 0:
        return 0.0
    if value > 0:
        return 100.0 / (value + 100.0)
    return abs(value) / (abs(value) + 100.0)


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["date"] = out["date"].astype(str).str[:10]
    out["market"] = out["market"].astype(str)
    out["marketFamily"] = out["market"].map(MARKET_FAMILY).fillna("other")

    out["line"] = out.get("line", 0).map(to_float)
    out["americanOdds"] = out.get("americanOdds", 0).map(to_float)
    out["sportsbookImpliedProbability"] = out["americanOdds"].map(american_to_implied)

    out["actualStat"] = out.get("actualStat", 0).map(to_float)
    out["label"] = out["label"].map(lambda value: int(to_float(value, 0)))

    out["awayScore"] = out.get("awayScore", 0).map(to_float)
    out["homeScore"] = out.get("homeScore", 0).map(to_float)
    out["awayFirstInningRuns"] = out.get("awayFirstInningRuns", 0).map(to_float)
    out["homeFirstInningRuns"] = out.get("homeFirstInningRuns", 0).map(to_float)
    out["awayFirstFiveRuns"] = out.get("awayFirstFiveRuns", 0).map(to_float)
    out["homeFirstFiveRuns"] = out.get("homeFirstFiveRuns", 0).map(to_float)

    out["gameTotalRunsFinal"] = out["awayScore"] + out["homeScore"]
    out["firstInningRunsFinal"] = out["awayFirstInningRuns"] + out["homeFirstInningRuns"]
    out["firstFiveRunsFinal"] = out["awayFirstFiveRuns"] + out["homeFirstFiveRuns"]

    out["team"] = out.get("gradedTeam", out.get("team", "")).map(clean)
    out["opponent"] = out.get("gradedOpponent", out.get("opponent", "")).map(clean)
    out["bookmaker"] = out.get("bookmaker", "").map(clean)

    out["isHomeTeam"] = (out["team"] == out.get("home", "").map(clean)).astype(int)
    out["isAwayTeam"] = (out["team"] == out.get("away", "").map(clean)).astype(int)

    out["isOver"] = out.get("side", "").astype(str).str.lower().str.contains("over", na=False).astype(int)
    out["isUnder"] = out.get("side", "").astype(str).str.lower().str.contains("under", na=False).astype(int)

    out["isMoneyline"] = out["marketFamily"].eq("moneyline").astype(int)
    out["isSpread"] = out["marketFamily"].eq("spread").astype(int)
    out["isTotal"] = out["marketFamily"].eq("total").astype(int)
    out["isTeamTotal"] = out["marketFamily"].eq("team_total").astype(int)
    out["isFirstScore"] = out["marketFamily"].eq("first_score").astype(int)

    return out


def build_training(input_path: Path, output_path: Path, summary_path: Path) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(f"Missing graded OddsPapi file: {input_path}")

    raw = pd.read_csv(input_path, low_memory=False)

    required = {"market", "graded", "label", "date"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"Input missing required columns: {missing}")

    df = raw[
        raw["market"].astype(str).isin(SUPPORTED_MARKETS)
        & raw["graded"].astype(str).eq("1")
        & raw["label"].astype(str).isin({"0", "1", "0.0", "1.0"})
    ].copy()

    df = add_basic_features(df)

    keep_cols = [
        "date",
        "fixtureId",
        "bookmaker",
        "market",
        "marketFamily",
        "team",
        "opponent",
        "away",
        "home",
        "line",
        "americanOdds",
        "sportsbookImpliedProbability",
        "isHomeTeam",
        "isAwayTeam",
        "isOver",
        "isUnder",
        "isMoneyline",
        "isSpread",
        "isTotal",
        "isTeamTotal",
        "isFirstScore",
        "actualStat",
        "label",
        "result",
        "awayScore",
        "homeScore",
        "awayFirstInningRuns",
        "homeFirstInningRuns",
        "awayFirstFiveRuns",
        "homeFirstFiveRuns",
        "gameTotalRunsFinal",
        "firstInningRunsFinal",
        "firstFiveRunsFinal",
    ]

    keep_cols = [col for col in keep_cols if col in df.columns]
    train = df[keep_cols].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    train.to_csv(output_path, index=False)

    summary = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "output": str(output_path),
        "rowsInput": int(len(raw)),
        "rowsTraining": int(len(train)),
        "markets": train["market"].value_counts().to_dict(),
        "labelsByMarket": (
            train.groupby(["market", "label"])
            .size()
            .reset_index(name="rows")
            .sort_values(["market", "label"])
            .to_dict(orient="records")
        ),
        "bookmakers": train["bookmaker"].value_counts().to_dict() if "bookmaker" in train.columns else {},
        "dateRange": {
            "min": str(train["date"].min()) if len(train) else "",
            "max": str(train["date"].max()) if len(train) else "",
        },
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build team/game market training rows from graded OddsPapi markets.")
    parser.add_argument(
        "--input",
        default=str(ODDSPAPI_DIR / "historical_game_markets_graded_2026.csv"),
    )
    parser.add_argument(
        "--output",
        default=str(ML_DIR / "team_game_markets_training_2026.csv"),
    )
    parser.add_argument(
        "--summary",
        default=str(ML_DIR / "team_game_markets_training_summary_2026.json"),
    )
    args = parser.parse_args()

    summary = build_training(Path(args.input), Path(args.output), Path(args.summary))

    print(json.dumps({
        "input": summary["input"],
        "output": summary["output"],
        "rowsInput": summary["rowsInput"],
        "rowsTraining": summary["rowsTraining"],
        "dateRange": summary["dateRange"],
        "markets": summary["markets"],
    }, indent=2))


if __name__ == "__main__":
    main()
