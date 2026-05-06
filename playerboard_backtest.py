from __future__ import annotations

"""Backtest saved Playerboard snapshots against completed game logs.

Input:
- data/playerboard/playerboard_2026.csv

Outputs:
- data/backtests/playerboard_backtest_2026.csv
- data/backtests/playerboard_backtest_summary_2026.json

Purpose:
- Build ML/backtesting-ready outcomes for every auto-ranked Playerboard prop.
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PLAYERBOARD_DIR = ROOT / "data" / "playerboard"
BACKTEST_DIR = ROOT / "data" / "backtests"
STATS_DIR = ROOT / "data" / "cache" / "incremental_stats"
SEASON_LOG_DIR = ROOT / "data" / "warehouse" / "season_logs"
CLOUD_SEASON_LOG_DIR = ROOT / "data" / "cloud" / "season_logs"

BACKTEST_FIELDS = [
    "snapshotAt",
    "gradedAt",
    "season",
    "date",
    "market",
    "player",
    "team",
    "opponent",
    "pitcher",
    "line",
    "americanOdds",
    "actualStat",
    "result",
    "profitUnits",
    "finalProbabilityPercent",
    "sportsbookImpliedPercent",
    "finalEdgePercent",
    "confidence",
    "recommendation",
    "weatherAdjustmentPercent",
    "savantAdjustmentPercent",
    "oddsMovementAdjustmentPercent",
    "missingData",
    "gradeNote",
]

SUMMARY_FIELDS = [
    "bucket",
    "name",
    "props",
    "graded",
    "wins",
    "losses",
    "pushes",
    "profitUnits",
    "winRate",
    "roiPercent",
]


def clean(value: Any) -> str:
    return str(value or "").strip()



def base_market(market: Any) -> str:
    text = clean(market)
    return text[:-4] if text.endswith("_alt") else text



def norm(value: Any) -> str:
    text = clean(value).lower()
    text = text.replace(".", "").replace(",", "")
    return " ".join(text.split())


def to_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric text to float, returning default for missing/invalid values.
    
    This helper is for aggregation/reporting where default=0.0 is intentional.
    Do not use it for ML feature extraction when missingness must stay explicit;
    use ml_prop_model.to_float() or a nullable parser instead.
    """
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def get_any(row: dict[str, Any], names: list[str]) -> str:
    lower = {clean(k).lower(): v for k, v in row.items()}
    for name in names:
        key = clean(name).lower()
        if key in lower and clean(lower[key]):
            return clean(lower[key])
    return ""


def playerboard_file(season: int) -> Path:
    return PLAYERBOARD_DIR / f"playerboard_{season}.csv"


def backtest_file(season: int) -> Path:
    return BACKTEST_DIR / f"playerboard_backtest_{season}.csv"


def summary_file(season: int) -> Path:
    return BACKTEST_DIR / f"playerboard_backtest_summary_{season}.json"


def first_existing_rows(paths: list[Path]) -> list[dict[str, str]]:
    for path in paths:
        rows = read_csv_rows(path)
        if rows:
            return rows
    return []


def batter_logs(season: int) -> list[dict[str, str]]:
    # Prefer fresh workflow/warehouse logs over older local incremental cache.
    return first_existing_rows([
        SEASON_LOG_DIR / f"batter_game_logs_{season}.csv",
        CLOUD_SEASON_LOG_DIR / f"batter_game_logs_{season}.csv",
        STATS_DIR / f"batter_game_logs_{season}.csv",
    ])


def pitcher_logs(season: int) -> list[dict[str, str]]:
    # Prefer fresh workflow/warehouse logs over older local incremental cache.
    return first_existing_rows([
        SEASON_LOG_DIR / f"pitcher_game_logs_{season}.csv",
        CLOUD_SEASON_LOG_DIR / f"pitcher_game_logs_{season}.csv",
        STATS_DIR / f"pitcher_game_logs_{season}.csv",
    ])


def find_batter_log(rows: list[dict[str, str]], date_label: str, player: str, team: str = "") -> dict[str, str]:
    target = norm(player)
    team = clean(team).upper()

    for row in rows:
        if clean(row.get("date")) != date_label:
            continue
        if norm(row.get("player")) != target:
            continue
        if team and clean(row.get("team")).upper() and clean(row.get("team")).upper() != team:
            continue
        return row

    return {}


def find_pitcher_log(rows: list[dict[str, str]], date_label: str, pitcher: str, team: str = "") -> dict[str, str]:
    target = norm(pitcher)
    team = clean(team).upper()

    for row in rows:
        if clean(row.get("date")) != date_label:
            continue
        if norm(row.get("player")) != target:
            continue
        if team and clean(row.get("team")).upper() and clean(row.get("team")).upper() != team:
            continue
        return row

    return {}


def actual_stat(row: dict[str, str], market: str, batter_rows: list[dict[str, str]], pitcher_rows: list[dict[str, str]]) -> tuple[float | None, str]:
    date_label = clean(row.get("date"))[:10]
    market = base_market(clean(row.get("market")))
    player = clean(row.get("player"))
    team = clean(row.get("team"))
    pitcher = clean(row.get("pitcher")) or player

    if market.startswith("batter"):
        log = find_batter_log(batter_rows, date_label, player, team)
        if not log:
            return None, "No batter game log found."

        if market == "batter_hits":
            return to_float(get_any(log, ["hits", "h"])), "Batter hits from game log."
        if market == "batter_total_bases":
            return to_float(get_any(log, ["totalBases", "total_bases", "tb"])), "Batter total bases from game log."
        if market == "batter_home_runs":
            return to_float(get_any(log, ["homeRuns", "home_runs", "hr"])), "Batter home runs from game log."
        if market == "batter_rbis":
            return to_float(get_any(log, ["rbi", "rbiS", "runsBattedIn", "runs_batted_in"])), "Batter RBIs from game log."
        if market == "batter_stolen_bases":
            return to_float(get_any(log, ["stolenBases", "stolen_bases", "sb"])), "Batter stolen bases from game log."

        return None, f"Unsupported batter market: {market}"

    if market.startswith("team"):
        # Team prop support is future-ready. It depends on team game logs
        # being populated with team-level runs and first-score fields.
        team = clean(row.get("team"))
        opponent = clean(row.get("opponent"))
        game_date = clean(row.get("date"))[:10]

        candidates = [
            r for r in batter_rows
            if clean(r.get("date"))[:10] == game_date
        ]

        # Prefer team rows if the caller starts passing a real team log here later.
        # For now, use any row shape that exposes team/runs fields.
        team_log = None
        for log in candidates:
            if clean(log.get("team")) == team:
                team_log = log
                break

        if market == "team_total_runs":
            if team_log:
                return to_float(get_any(team_log, ["runs", "teamRuns", "team_runs"])), "Team total runs from team/game log."
            return None, "Team total runs requires team game log rows."

        if market == "team_first_to_score":
            if team_log:
                value = get_any(team_log, ["firstToScore", "first_to_score", "teamFirstToScore"])
                if clean(value):
                    return to_float(value), "Team first-to-score flag from team/game log."
            return None, "Team first-to-score requires team first-score data."

        return None, f"Unsupported team market: {market}"

    if market.startswith("pitcher"):
        log = find_pitcher_log(pitcher_rows, date_label, pitcher, team)
        if not log:
            return None, "No pitcher game log found."

        if market == "pitcher_strikeouts":
            return to_float(get_any(log, ["strikeOuts", "strikeouts", "strike_outs", "so", "k"])), "Pitcher strikeouts from game log."
        if market == "pitcher_hits_allowed":
            return to_float(get_any(log, ["hits", "h"])), "Pitcher hits allowed from game log."
        if market == "pitcher_earned_runs":
            return to_float(get_any(log, ["earnedRuns", "earned_runs", "er"])), "Pitcher earned runs from game log."

        return None, f"Unsupported pitcher market: {market}"

    return None, f"Unsupported market: {market}"


def grade_over(actual: float, line: float) -> str:
    if actual > line:
        return "win"
    if actual == line:
        return "push"
    return "loss"


def american_profit_units(american_odds: Any, result: str) -> float:
    odds = to_float(american_odds)

    if result == "push":
        return 0.0
    if result != "win":
        return -1.0

    if odds > 0:
        return round(odds / 100, 4)
    if odds < 0:
        return round(100 / abs(odds), 4)

    return 0.0


def edge_bucket(edge: Any) -> str:
    value = to_float(edge)

    if value < 0:
        return "< 0%"
    if value < 2:
        return "0% to 2%"
    if value < 4:
        return "2% to 4%"
    if value < 6:
        return "4% to 6%"
    return "6%+"


def adjustment_bucket(value: Any, label: str) -> str:
    n = to_float(value)
    if n > 0:
        return f"{label} positive"
    if n < 0:
        return f"{label} negative"
    return f"{label} neutral"


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Avoid grading the exact same snapshot row multiple times."""
    seen = set()
    out = []

    for row in rows:
        key = (
            clean(row.get("snapshotAt")),
            clean(row.get("date")),
            clean(row.get("market")),
            norm(row.get("player")),
            clean(row.get("team")).upper(),
            clean(row.get("opponent")).upper(),
            clean(row.get("line")),
            clean(row.get("americanOdds")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)

    return out


def grade_playerboard(season: int = 2026) -> dict[str, Any]:
    board_rows = dedupe_rows(read_csv_rows(playerboard_file(season)))
    batter_rows = batter_logs(season)
    pitcher_rows = pitcher_logs(season)

    graded_at = now_iso()
    out = []

    for row in board_rows:
        actual, note = actual_stat(row, clean(row.get("market")), batter_rows, pitcher_rows)

        if actual is None:
            result = "ungraded"
            profit = 0.0
        else:
            result = grade_over(actual, to_float(row.get("line")))
            profit = american_profit_units(row.get("americanOdds"), result)

        out.append({
            "snapshotAt": clean(row.get("snapshotAt")),
            "gradedAt": graded_at,
            "season": clean(row.get("season")) or season,
            "date": clean(row.get("date"))[:10],
            "market": clean(row.get("market")),
            "player": clean(row.get("player")),
            "team": clean(row.get("team")),
            "opponent": clean(row.get("opponent")),
            "pitcher": clean(row.get("pitcher")),
            "line": clean(row.get("line")),
            "americanOdds": clean(row.get("americanOdds")),
            "actualStat": "" if actual is None else actual,
            "result": result,
            "profitUnits": profit,
            "finalProbabilityPercent": clean(row.get("finalProbabilityPercent")),
            "sportsbookImpliedPercent": clean(row.get("sportsbookImpliedPercent")),
            "finalEdgePercent": clean(row.get("finalEdgePercent")),
            "confidence": clean(row.get("confidence")),
            "recommendation": clean(row.get("recommendation")),
            "weatherAdjustmentPercent": clean(row.get("weatherAdjustmentPercent")),
            "savantAdjustmentPercent": clean(row.get("savantAdjustmentPercent")),
            "oddsMovementAdjustmentPercent": clean(row.get("oddsMovementAdjustmentPercent")),
            "missingData": clean(row.get("missingData")),
            "gradeNote": note,
        })

    write_csv(backtest_file(season), BACKTEST_FIELDS, out)

    summary = summarize_backtest(season, out)
    write_json(summary_file(season), summary)

    return summary


def summarize_group(rows: list[dict[str, Any]], bucket: str, key_fn) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        name = clean(key_fn(row)) or "Unknown"
        groups.setdefault(name, []).append(row)

    output = []

    for name, items in groups.items():
        graded = [r for r in items if r.get("result") in {"win", "loss", "push"}]
        wins = sum(1 for r in graded if r.get("result") == "win")
        losses = sum(1 for r in graded if r.get("result") == "loss")
        pushes = sum(1 for r in graded if r.get("result") == "push")
        risked = wins + losses
        profit = round(sum(to_float(r.get("profitUnits")) for r in graded), 4)

        output.append({
            "bucket": bucket,
            "name": name,
            "props": len(items),
            "graded": len(graded),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "profitUnits": profit,
            "winRate": round((wins / risked) * 100, 2) if risked else 0,
            "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        })

    return sorted(output, key=lambda r: to_float(r.get("profitUnits")), reverse=True)


def summarize_backtest(season: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    graded = [r for r in rows if r.get("result") in {"win", "loss", "push"}]
    wins = sum(1 for r in graded if r.get("result") == "win")
    losses = sum(1 for r in graded if r.get("result") == "loss")
    pushes = sum(1 for r in graded if r.get("result") == "push")
    risked = wins + losses
    profit = round(sum(to_float(r.get("profitUnits")) for r in graded), 4)

    breakdowns = []
    breakdowns.extend(summarize_group(rows, "market", lambda r: r.get("market")))
    breakdowns.extend(summarize_group(rows, "edgeBucket", lambda r: edge_bucket(r.get("finalEdgePercent"))))
    breakdowns.extend(summarize_group(rows, "confidence", lambda r: r.get("confidence")))
    breakdowns.extend(summarize_group(rows, "recommendation", lambda r: r.get("recommendation")))
    breakdowns.extend(summarize_group(rows, "savant", lambda r: adjustment_bucket(r.get("savantAdjustmentPercent"), "Savant")))
    breakdowns.extend(summarize_group(rows, "weather", lambda r: adjustment_bucket(r.get("weatherAdjustmentPercent"), "Weather")))
    breakdowns.extend(summarize_group(rows, "oddsMovement", lambda r: adjustment_bucket(r.get("oddsMovementAdjustmentPercent"), "Odds movement")))

    return {
        "season": season,
        "updatedAt": now_iso(),
        "props": len(rows),
        "graded": len(graded),
        "ungraded": len(rows) - len(graded),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "profitUnits": profit,
        "winRate": round((wins / risked) * 100, 2) if risked else 0,
        "roiPercent": round((profit / risked) * 100, 2) if risked else 0,
        "backtestFile": str(backtest_file(season)),
        "summaryFile": str(summary_file(season)),
        "breakdowns": breakdowns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest saved Playerboard snapshots.")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    print(json.dumps(grade_playerboard(args.season), indent=2))


if __name__ == "__main__":
    main()
