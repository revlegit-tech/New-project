from __future__ import annotations

"""Simple daily ML workflow for the Baseball Prop Predictor.

Examples:
    python daily_ml_workflow.py before --date 2026-05-03
    python daily_ml_workflow.py after --date 2026-05-03
    python daily_ml_workflow.py status

Important:
    Keep the app running locally, or set BASEBALL_PROP_APP_URL to the running app URL.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_URL = (os.environ.get("BASEBALL_PROP_APP_URL") or os.environ.get("APP_BASE_URL") or "http://127.0.0.1:8766").rstrip("/")
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.daily_workflow_service import DailyWorkflowService

ACTION_HEADER_NAME = "X-Baseball-Prop-Action"
ACTION_HEADER_VALUE = "1"

PROP_MARKETS = [
    "pitcher_strikeouts",
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "batter_rbis",
    "batter_stolen_bases",
    "batter_walks",
    "batter_singles",
    "batter_doubles",
    "batter_runs",
    "batter_2plus_hits",
    "batter_2plus_home_runs",
    "batter_2plus_rbis",
    "batter_3plus_rbis",
    "pitcher_outs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def season_from_date(date_text: str) -> int:
    return int(date_text[:4])


def print_header(title: str) -> None:
    print("")
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def request_json(path: str, method: str = "GET") -> dict:
    url = BASE_URL + path
    headers = {"User-Agent": "baseball-prop-predictor"}
    if method.upper() == "POST":
        headers[ACTION_HEADER_NAME] = ACTION_HEADER_VALUE
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception as error:
        raise RuntimeError(
            f"Could not reach {url}. Make sure the app is running and BASEBALL_PROP_APP_URL points to it.\n{error}"
        ) from error

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Endpoint returned non-JSON from {url}:\n{text[:300]}") from error

    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(payload["error"])

    return payload


def run_command(command: list[str], allow_fail: bool = True) -> int:
    print("")
    print("Running:", " ".join(command))
    result = subprocess.run(command)

    if result.returncode != 0 and not allow_fail:
        raise SystemExit(result.returncode)

    return result.returncode


def before_game(date_label: str) -> None:
    print_header(f"Before Game Setup: {date_label}")

    markets = ",".join(PROP_MARKETS)

    props = request_json(
        f"/api/admin/propline/props/sync?markets={urllib.parse.quote(markets)}&date={urllib.parse.quote(date_label)}",
        method="POST",
    )

    print("")
    print("Props pulled")
    print("------------")
    print(f"Sport: {props.get('sport', 'baseball_mlb')}")
    print(f"Markets: {', '.join(props.get('markets', PROP_MARKETS))}")
    print(f"Events: {props.get('eventCount', '--')}")
    print(f"Props: {props.get('propCount', '--')}")
    print(f"Saved: {props.get('savedPath', '--')}")

    board = request_json(
        f"/api/playerboard?season={season_from_date(date_label)}&date={urllib.parse.quote(date_label)}&limit=1000&refresh=1&save=1&replaceDate=1&sourceMode=propline",
    )

    print("")
    print("Playerboard built")
    print("-----------------")
    print(f"Props loaded: {board.get('propsLoaded', '--')}")
    print(f"Cards built: {board.get('cardsBuilt', '--')}")
    if board.get("saved"):
        print(f"Saved: {board.get('saved', {}).get('file', '--')}")

    template = request_json(
        f"/api/pipeline/create-template?date={urllib.parse.quote(date_label)}",
        method="POST",
    )

    print("")
    print("Game odds template created")
    print("--------------------------")
    print(f"Games: {template.get('games', '--')}")
    print(f"Rows: {template.get('rows', '--')}")
    print(f"Output: {template.get('output', '--')}")

    print("")
    print("Next step")
    print("---------")
    print("Open this file and fill at least team_moneyline, opponent_moneyline, and game_total:")
    print(template.get("output", f"data/imports/game_odds_template_{date_label}.csv"))
    print("")
    print("Then after games are final, run:")
    print(f"python daily_ml_workflow.py after --date {date_label}")


def after_game(date_label: str) -> None:
    print_header(f"After Game Update: {date_label}")

    print("")
    print("Step 1: Grade props")
    print("-------------------")
    grade = request_json(f"/api/pipeline/grade?date={urllib.parse.quote(date_label)}", method="POST")
    print(json.dumps(grade, indent=2))

    print("")
    print("Step 2: Merge game odds")
    print("-----------------------")
    merge = request_json(f"/api/pipeline/merge-game-odds?date={urllib.parse.quote(date_label)}", method="POST")
    print(json.dumps(merge, indent=2))

    print("")
    print("Step 3: Prepare/train player-prop markets")
    print("-----------------------------------------")
    for market in PROP_MARKETS:
        run_command([sys.executable, str(ROOT / "prepare_market_training.py"), "--market", market, "--train"], allow_fail=True)

    print("")
    print("Step 4: Prepare/train moneyline model")
    print("-------------------------------------")
    season = season_from_date(date_label)
    run_command(
        [
            sys.executable,
            str(ROOT / "prepare_moneyline_training.py"),
            "--season",
            str(season),
            "--start-date",
            f"{season}-03-01",
            "--end-date",
            date_label,
            "--train",
        ],
        allow_fail=True,
    )

    print("")
    print("Done")
    print("----")
    print("The workflow finished. Some player-prop markets may still say they need more data.")
    print("That is normal until each market has both over=0 and over=1 rows.")


def status() -> None:
    print_header("ML Training Status")

    try:
        payload = request_json("/api/prop-ml/status")
    except Exception as error:
        print(error)
        return

    for row in payload.get("markets", []):
        print("")
        print(row.get("market", "--"))
        print("-" * len(row.get("market", "--")))
        print(f"Rows: {row.get('trainingRows', 0)}")
        print(f"Classes: {row.get('classCounts', {})}")
        print(f"Can train: {'yes' if row.get('canTrain') else 'no'}")
        print(f"Status: {row.get('status', '--')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple daily ML workflow.")
    parser.add_argument("--launch-mode", action="store_true", help="Run lightweight launch bootstrap and exit.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD or today for --launch-mode / run-daily.")
    sub = parser.add_subparsers(dest="command")

    before = sub.add_parser("before")
    before.add_argument("--date", default=today())

    after = sub.add_parser("after")
    after.add_argument("--date", default=today())

    sub.add_parser("status")
    sub.add_parser("run-daily")

    args = parser.parse_args()

    if args.launch_mode:
      from mlb_app.services.launch_bootstrap_service import LaunchBootstrapService

      date_label = args.date or today()
      if date_label == "today":
        date_label = today()
      payload = LaunchBootstrapService(Settings.from_env(ROOT)).run(date_text=date_label)
      print(json.dumps(payload, indent=2, sort_keys=True))
      return

    if not args.command:
      parser.error("command is required unless --launch-mode is used")

    if args.command == "before":
      before_game(args.date)
    elif args.command == "after":
      after_game(args.date)
    elif args.command == "status":
      status()
    elif args.command == "run-daily":
      date_label = args.date or today()
      if date_label == "today":
        date_label = today()
      payload = DailyWorkflowService(Settings.from_env(ROOT)).run(date_text=date_label)
      print(json.dumps(payload, indent=2, sort_keys=True))
      status = str(payload.get("verificationSummary", {}).get("status") or payload.get("status") or "").lower()
      if status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
