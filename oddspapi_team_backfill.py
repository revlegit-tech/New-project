from local_env import load_local_env
load_local_env()
import argparse
import csv
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pandas as pd

BASE_URL = os.environ.get("ODDSPAPI_BASE_URL", "https://api.oddspapi.io/v4").rstrip("/")
API_KEY = os.environ.get("ODDSPAPI_KEY", "").strip()

SPORT_ID = 13
MLB_TOURNAMENT_ID = 109
BOOKMAKERS = ["fanduel", "draftkings", "betmgm"]

OUT_DIR = Path("data/cache/oddspapi")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def require_key():
    if not API_KEY:
        raise SystemExit("Missing ODDSPAPI_KEY environment variable.")


def request_json(endpoint, params, sleep_seconds=5.2):
    require_key()

    params = dict(params)
    params["apiKey"] = API_KEY

    full_url = f"{BASE_URL}/{endpoint.lstrip('/')}?{urlencode(params)}"
    redacted = full_url.replace(API_KEY, "***")

    print("\n" + "=" * 100)
    print("GET", redacted)

    req = Request(
        full_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "New-project-OddsPapi-team-backfill/1.0",
        },
    )

    try:
        with urlopen(req, timeout=75) as resp:
            status = resp.status
            text = resp.read().decode("utf-8", errors="replace")
            headers = dict(resp.headers.items())
    except HTTPError as exc:
        status = exc.code
        text = exc.read().decode("utf-8", errors="replace")
        headers = dict(exc.headers.items())
        print("HTTP ERROR:", status)
    except URLError as exc:
        print("URL ERROR:", exc)
        return {
            "ok": False,
            "status": None,
            "endpoint": endpoint,
            "params": {k: ("***" if k == "apiKey" else v) for k, v in params.items()},
            "error": str(exc),
        }

    try:
        data = json.loads(text) if text else None
    except json.JSONDecodeError:
        data = {"rawText": text[:20000]}

    payload = {
        "ok": 200 <= status < 300,
        "status": status,
        "endpoint": endpoint,
        "params": {k: ("***" if k == "apiKey" else v) for k, v in params.items()},
        "headers": headers,
        "data": data,
    }

    print("status:", status)

    if sleep_seconds:
        time.sleep(sleep_seconds)

    return payload


def load_markets():
    markets_path = OUT_DIR / "markets.json"

    if markets_path.exists():
        payload = json.loads(markets_path.read_text(encoding="utf-8"))
        data = payload.get("data", [])
        if data:
            return data

    print("markets.json missing or empty; pulling /markets metadata.")
    payload = request_json("markets", {"sportId": SPORT_ID}, sleep_seconds=1.0)
    markets_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload.get("data", [])


def decimal_to_american(price):
    try:
        price = float(price)
    except Exception:
        return ""

    if price <= 1:
        return ""

    if price >= 2:
        return round((price - 1) * 100)

    return round(-100 / (price - 1))


def get_fixture_rows(start_date, end_date):
    payload = request_json(
        "fixtures",
        {
            "sportId": SPORT_ID,
            "tournamentId": MLB_TOURNAMENT_ID,
            "from": start_date,
            "to": end_date,
        },
        sleep_seconds=1.0,
    )

    out_file = OUT_DIR / f"fixtures_mlb_{start_date}_to_{end_date}.json"
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = []
        for value in data.values():
            if isinstance(value, list):
                rows.extend(value)
        if not rows:
            rows = [data]
    else:
        rows = []

    fixtures = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("tournamentId")) == str(MLB_TOURNAMENT_ID):
            fixtures.append(row)

    fixtures_path = OUT_DIR / f"mlb_fixture_candidates_{start_date}_to_{end_date}.json"
    fixtures_path.write_text(json.dumps(fixtures, indent=2, ensure_ascii=False), encoding="utf-8")

    print("fixtures:", len(fixtures))
    print("saved:", fixtures_path)
    return fixtures


def pull_historical_odds_for_fixture(fixture, bookmakers):
    fixture_id = fixture.get("fixtureId")
    if not fixture_id:
        return None

    out_file = OUT_DIR / f"historical_odds_{fixture_id}_{'_'.join(bookmakers)}.json"

    if out_file.exists():
        print("already exists, skipping pull:", out_file)
        return json.loads(out_file.read_text(encoding="utf-8"))

    payload = request_json(
        "historical-odds",
        {
            "fixtureId": fixture_id,
            "bookmakers": ",".join(bookmakers),
        },
        sleep_seconds=5.2,
    )

    payload["fixture"] = fixture
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("saved:", out_file)

    return payload


def flatten_team_props(payload, market_lookup, outcome_lookup):
    fixture = payload.get("fixture", {})
    data = payload.get("data", {})
    bookmakers = data.get("bookmakers", {}) if isinstance(data, dict) else {}

    team1 = fixture.get("participant1Abbr", "")
    team2 = fixture.get("participant2Abbr", "")

    rows = []

    for bookmaker_slug, bookmaker_payload in bookmakers.items():
        markets = bookmaker_payload.get("markets", {}) if isinstance(bookmaker_payload, dict) else {}

        for market_id, market_payload in markets.items():
            market_meta = market_lookup.get(str(market_id), {})
            market_type = str(market_meta.get("marketType", "")).lower()
            market_name = market_meta.get("marketName", "")
            line = market_meta.get("handicap", "")

            if market_type == "teamtotals-team1":
                mapped_market = "team_total_runs"
                base_team, base_opponent = team1, team2
            elif market_type == "teamtotals-team2":
                mapped_market = "team_total_runs"
                base_team, base_opponent = team2, team1
            elif market_type == "firsttoscorearun":
                mapped_market = "team_first_to_score"
                base_team, base_opponent = "", ""
            else:
                continue

            outcomes = market_payload.get("outcomes", {}) if isinstance(market_payload, dict) else {}

            for outcome_id, outcome_payload in outcomes.items():
                outcome_meta = outcome_lookup.get(str(outcome_id), {})
                outcome_name = outcome_meta.get("outcomeName", "")

                row_team = base_team
                row_opponent = base_opponent

                if mapped_market == "team_first_to_score":
                    if outcome_name == "1":
                        row_team, row_opponent = team1, team2
                    elif outcome_name == "2":
                        row_team, row_opponent = team2, team1
                    else:
                        continue

                players = outcome_payload.get("players", {}) if isinstance(outcome_payload, dict) else {}

                for _, history in players.items():
                    if not isinstance(history, list):
                        continue

                    for item in history:
                        if not isinstance(item, dict):
                            continue

                        price = item.get("price", "")
                        rows.append({
                            "fixtureId": data.get("fixtureId", fixture.get("fixtureId", "")),
                            "startTime": fixture.get("startTime", ""),
                            "date": str(fixture.get("startTime", ""))[:10],
                            "bookmaker": bookmaker_slug,
                            "market": mapped_market,
                            "team": row_team,
                            "opponent": row_opponent,
                            "line": line,
                            "marketId": market_id,
                            "marketType": market_type,
                            "marketName": market_name,
                            "outcomeId": outcome_id,
                            "outcomeName": outcome_name,
                            "decimalOdds": price,
                            "americanOdds": decimal_to_american(price),
                            "active": item.get("active", ""),
                            "createdAt": item.get("createdAt", ""),
                        })

    return rows


def latest_pregame_rows(df):
    if df.empty:
        return df

    df = df.copy()
    df["createdAt"] = pd.to_datetime(df["createdAt"], utc=True, errors="coerce")
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True, errors="coerce")

    pre = df[
        df["createdAt"].notna()
        & df["startTime"].notna()
        & (df["createdAt"] <= df["startTime"])
    ].copy()

    if pre.empty:
        return pre

    active = pre[pre["active"].astype(str).str.lower().isin(["true", "1"])].copy()
    source = active if len(active) else pre

    keys = [
        "fixtureId",
        "date",
        "bookmaker",
        "market",
        "team",
        "opponent",
        "line",
        "outcomeName",
    ]

    return (
        source.sort_values("createdAt")
        .groupby(keys, dropna=False)
        .tail(1)
        .sort_values(["date", "fixtureId", "market", "team", "line", "outcomeName", "bookmaker"])
    )


def grade_with_manual_scores(latest, manual_scores_path):
    if latest.empty:
        return latest

    scores_path = Path(manual_scores_path)
    if not scores_path.exists():
        print("manual scores file not found, skipping grading:", scores_path)
        return pd.DataFrame()

    scores = pd.read_csv(scores_path)

    required = {"date", "team", "runs", "firstToScore"}
    missing = sorted(required - set(scores.columns))
    if missing:
        raise SystemExit(f"Manual score file missing columns: {missing}")

    scores["date"] = scores["date"].astype(str).str[:10]
    scores["team"] = scores["team"].astype(str).str.upper()
    latest = latest.copy()
    latest["date"] = latest["date"].astype(str).str[:10]
    latest["team"] = latest["team"].astype(str).str.upper()

    score_map = {
        (row["date"], row["team"]): row
        for _, row in scores.iterrows()
    }

    graded_rows = []

    for _, row in latest.iterrows():
        market = row["market"]
        team = row["team"]
        key = (row["date"], team)

        score = score_map.get(key)
        if score is None:
            continue

        if market == "team_total_runs":
            if str(row["outcomeName"]).lower() != "over":
                continue

            actual = float(score["runs"])
            line = float(row["line"])
            over = int(actual > line)
            result = "over" if over else "under"

        elif market == "team_first_to_score":
            first_value = score["firstToScore"]
            try:
                actual = int(float(first_value) > 0)
            except Exception:
                actual = int(str(first_value).strip().lower() in {"1", "1.0", "true", "yes", "y"})
            over = actual
            result = "win" if actual else "loss"

        else:
            continue

        out = row.to_dict()
        out["actualStat"] = actual
        out["over"] = over
        out["result"] = result
        out["source"] = "oddspapi"
        out["season"] = int(str(row["date"])[:4])
        graded_rows.append(out)

    return pd.DataFrame(graded_rows)


def write_manual_score_template(fixtures, start_date, end_date):
    rows = []
    for fixture in fixtures:
        date_label = str(fixture.get("startTime", ""))[:10]
        team1 = fixture.get("participant1Abbr", "")
        team2 = fixture.get("participant2Abbr", "")
        fixture_id = fixture.get("fixtureId", "")

        rows.append({
            "fixtureId": fixture_id,
            "date": date_label,
            "team": team1,
            "opponent": team2,
            "runs": "",
            "firstToScore": "",
        })
        rows.append({
            "fixtureId": fixture_id,
            "date": date_label,
            "team": team2,
            "opponent": team1,
            "runs": "",
            "firstToScore": "",
        })

    out = OUT_DIR / f"manual_team_scores_template_{start_date}_to_{end_date}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print("manual score template:", out)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--max-fixtures", type=int, default=3)
    parser.add_argument("--manual-scores", default="")
    parser.add_argument("--skip-pull", action="store_true")
    args = parser.parse_args()

    markets = load_markets()
    market_lookup = {str(m.get("marketId")): m for m in markets}

    outcome_lookup = {}
    for market in markets:
        for outcome in market.get("outcomes", []) or []:
            outcome_lookup[str(outcome.get("outcomeId"))] = outcome

    fixtures = get_fixture_rows(args.from_date, args.to_date)
    fixtures = fixtures[: max(args.max_fixtures, 0)]

    # Only create a blank manual score template when the user is not supplying
    # an existing score file. This prevents grading runs from overwriting filled scores.
    if not args.manual_scores:
        write_manual_score_template(fixtures, args.from_date, args.to_date)
    else:
        score_path = Path(args.manual_scores)
        if score_path.exists():
            print("using manual scores:", score_path)
        else:
            write_manual_score_template(fixtures, args.from_date, args.to_date)
            print("manual scores file missing; created blank template:", score_path)

    all_flattened = []

    for i, fixture in enumerate(fixtures, start=1):
        print("\n" + "#" * 100)
        print(f"Fixture {i}/{len(fixtures)}:", fixture.get("fixtureId"), fixture.get("participant1Abbr"), "vs", fixture.get("participant2Abbr"))

        if args.skip_pull:
            fixture_id = fixture.get("fixtureId")
            hist_file = OUT_DIR / f"historical_odds_{fixture_id}_{'_'.join(BOOKMAKERS)}.json"
            if not hist_file.exists():
                print("missing cached historical file:", hist_file)
                continue
            payload = json.loads(hist_file.read_text(encoding="utf-8"))
        else:
            payload = pull_historical_odds_for_fixture(fixture, BOOKMAKERS)

        if not payload or not payload.get("ok"):
            print("skipping unsuccessful payload")
            continue

        rows = flatten_team_props(payload, market_lookup, outcome_lookup)
        print("flattened rows:", len(rows))
        all_flattened.extend(rows)

    flat_df = pd.DataFrame(all_flattened)

    flat_out = OUT_DIR / f"historical_team_props_flattened_{args.from_date}_to_{args.to_date}.csv"
    latest_out = OUT_DIR / f"historical_team_props_pregame_latest_{args.from_date}_to_{args.to_date}.csv"
    graded_out = OUT_DIR / f"historical_team_props_graded_{args.from_date}_to_{args.to_date}.csv"

    flat_df.to_csv(flat_out, index=False)
    print("\nflat output:", flat_out)
    print("flat rows:", len(flat_df))

    latest = latest_pregame_rows(flat_df)
    latest.to_csv(latest_out, index=False)
    print("latest pregame output:", latest_out)
    print("latest rows:", len(latest))

    if not latest.empty:
        print("\nLatest rows by market:")
        print(latest["market"].value_counts(dropna=False).to_string())

    if args.manual_scores:
        graded = grade_with_manual_scores(latest, args.manual_scores)
        graded.to_csv(graded_out, index=False)
        print("graded output:", graded_out)
        print("graded rows:", len(graded))

        if not graded.empty:
            print("\nGraded rows by market:")
            print(graded["market"].value_counts(dropna=False).to_string())
            print("\nClass counts:")
            print(graded.groupby(["market", "over"]).size().reset_index(name="rows").to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
