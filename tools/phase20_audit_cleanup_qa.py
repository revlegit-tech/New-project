from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    payload: Any = None
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = None
    return {
        "cmd": " ".join(args),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "json": payload,
    }


def edge_direct(date: str, market: str) -> dict[str, Any]:
    try:
        from mlb_app.services.edge_board_service import EdgeBoardService

        payload = EdgeBoardService().payload({
            "date": [date],
            "market": [market],
            "limit": ["5"],
            "refresh": ["1"],
        })
        rows = payload.get("rows") or []
        fields = [
            "team_moneyline", "opponent_moneyline", "game_total", "moneyline_implied_probability",
            "team_implied_runs", "opponent_implied_runs", "weather_temperature_f", "weather_wind_mph",
            "weather_humidity", "weather_wind_direction", "roof_status", "open_team_moneyline",
            "moneyline_move", "open_game_total", "total_move",
        ]
        sample = [
            {"player": row.get("player"), "team": row.get("team"), "opponent": row.get("opponent"), **{field: row.get(field, "") for field in fields}}
            for row in rows[:5]
        ]
        missing = {field: sum(1 for row in sample if not str(row.get(field, "")).strip()) for field in fields}
        return {"status": "ok", "rows": len(rows), "sample": sample, "missingByFieldInSample": missing}
    except Exception as error:  # noqa: BLE001
        return {"status": "error", "error": str(error)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 20 QA for polished context UI and audit cleanup.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--markets", nargs="+", default=["batter_hits", "batter_total_bases"])
    parser.add_argument("--market", default="batter_hits")
    args = parser.parse_args()

    report = {
        "status": "ok",
        "date": args.date,
        "directEdgeBoard": edge_direct(args.date, args.market),
        "phase16Audit": run([sys.executable, "tools/phase16_live_feature_audit.py", "--date", args.date, "--season", str(args.season), "--markets", *args.markets, "--write"]),
        "phase17Audit": run([sys.executable, "tools/phase17_game_context_audit.py", "--date", args.date, "--season", str(args.season), "--markets", *args.markets, "--write"]),
    }
    if report["directEdgeBoard"].get("status") != "ok":
        report["status"] = "warning"
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
