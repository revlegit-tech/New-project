from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ODDSPAPI_DIR = Path("data/cache/oddspapi")
BOOKMAKERS = ("fanduel", "draftkings", "betmgm")


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def decimal_to_american(decimal_odds: Any) -> int | None:
    dec = to_float(decimal_odds)
    if not dec or dec <= 1:
        return None
    if dec >= 2:
        return int(round((dec - 1) * 100))
    return int(round(-100 / (dec - 1)))


def load_markets() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    path = ODDSPAPI_DIR / "markets.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    market_by_id: dict[str, dict[str, Any]] = {}
    outcome_by_id: dict[str, dict[str, Any]] = {}

    for market in payload.get("data", []):
        if str(market.get("sportId")) != "13":
            continue
        if market.get("playerProp"):
            continue

        market_id = clean(market.get("marketId"))
        if not market_id:
            continue

        market_by_id[market_id] = market

        for outcome in market.get("outcomes", []) or []:
            outcome_id = clean(outcome.get("outcomeId"))
            if outcome_id:
                outcome_by_id[outcome_id] = {
                    **outcome,
                    "_marketId": market_id,
                    "_marketType": market.get("marketType"),
                    "_marketName": market.get("marketName"),
                }

    return market_by_id, outcome_by_id


def mapped_market(market: dict[str, Any]) -> str:
    market_type = clean(market.get("marketType")).lower()
    name = clean(market.get("marketName")).lower()
    period = clean(market.get("period")).lower()

    if market_type == "moneyline" and period == "result":
        return "moneyline"

    if market_type == "totals":
        if period == "result":
            return "game_total_runs"
        if period == "p1+p2+p3+p4+p5" or "first to fifth" in name:
            return "first_five_total_runs"
        if period == "p1":
            return "first_inning_total_runs"
        if period == "p2":
            return "second_inning_total_runs"
        if period == "p3":
            return "third_inning_total_runs"
        if period == "p4":
            return "fourth_inning_total_runs"
        if period == "p5":
            return "fifth_inning_total_runs"
        if period == "p6":
            return "sixth_inning_total_runs"
        if period == "p7":
            return "seventh_inning_total_runs"
        if period == "p8":
            return "eighth_inning_total_runs"
        if period == "p9":
            return "ninth_inning_total_runs"

    if market_type == "spreads":
        if period == "result":
            return "run_line"
        if period == "p1+p2+p3+p4+p5" or "first to fifth" in name:
            return "run_line_first_five"
        if period == "p1":
            return "run_line_first_inning"
        if period == "p2":
            return "run_line_second_inning"
        if period == "p3":
            return "run_line_third_inning"
        if period == "p4":
            return "run_line_fourth_inning"
        if period == "p5":
            return "run_line_fifth_inning"
        if period == "p6":
            return "run_line_sixth_inning"
        if period == "p7":
            return "run_line_seventh_inning"
        if period == "p8":
            return "run_line_eighth_inning"
        if period == "p9":
            return "run_line_ninth_inning"

    return ""


def fixture_team_names(raw: dict[str, Any]) -> tuple[str, str, str, str]:
    fixture = raw.get("fixture") or {}
    data = raw.get("data") or {}

    fixture_id = clean(
        fixture.get("fixtureId")
        or fixture.get("id")
        or data.get("fixtureId")
        or (raw.get("params") or {}).get("fixtureId")
    )

    # Try common fixture shapes first.
    candidates = [
        fixture,
        data.get("fixture") if isinstance(data.get("fixture"), dict) else {},
    ]

    team1 = ""
    team2 = ""

    for item in candidates:
        if not isinstance(item, dict):
            continue

        team1 = clean(
            item.get("participant1Abbr")
            or item.get("team1")
            or item.get("home")
            or item.get("homeTeam")
            or item.get("participant1")
            or item.get("participant1Name")
            or item.get("competitor1")
        )
        team2 = clean(
            item.get("participant2Abbr")
            or item.get("team2")
            or item.get("away")
            or item.get("awayTeam")
            or item.get("participant2")
            or item.get("participant2Name")
            or item.get("competitor2")
        )

        participants = item.get("participants")
        if isinstance(participants, list) and len(participants) >= 2:
            team1 = team1 or clean(participants[0].get("name") if isinstance(participants[0], dict) else participants[0])
            team2 = team2 or clean(participants[1].get("name") if isinstance(participants[1], dict) else participants[1])

        if team1 and team2:
            break

    if not (team1 and team2):
        # Fallback from historical candidate files.
        for candidate_path in sorted(ODDSPAPI_DIR.glob("mlb_fixture_candidates_*.json"), reverse=True):
            try:
                payload = json.loads(candidate_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            if isinstance(payload, list):
                pool = payload
            elif isinstance(payload, dict):
                pool = payload.get("data", payload)
                if isinstance(pool, dict):
                    pool = pool.get("fixtures", pool.get("items", []))
            else:
                pool = []

            if not isinstance(pool, list):
                continue

            for fx in pool:
                if not isinstance(fx, dict):
                    continue
                fx_id = clean(fx.get("fixtureId") or fx.get("id"))
                if fx_id != fixture_id:
                    continue

                team1 = clean(
                    fx.get("participant1Abbr")
                    or fx.get("team1")
                    or fx.get("home")
                    or fx.get("homeTeam")
                    or fx.get("participant1")
                    or fx.get("participant1Name")
                )
                team2 = clean(
                    fx.get("participant2Abbr")
                    or fx.get("team2")
                    or fx.get("away")
                    or fx.get("awayTeam")
                    or fx.get("participant2")
                    or fx.get("participant2Name")
                )

                participants = fx.get("participants")
                if isinstance(participants, list) and len(participants) >= 2:
                    team1 = team1 or clean(participants[0].get("name") if isinstance(participants[0], dict) else participants[0])
                    team2 = team2 or clean(participants[1].get("name") if isinstance(participants[1], dict) else participants[1])

                if team1 and team2:
                    start_time = clean(fx.get("startTime") or fixture.get("startTime") or data.get("startTime"))
                    return fixture_id, team1, team2, start_time

    start_time = clean(fixture.get("startTime") or data.get("startTime"))
    return fixture_id, team1, team2, start_time


def latest_price(prices: Any) -> dict[str, Any] | None:
    if isinstance(prices, list):
        active = [p for p in prices if isinstance(p, dict) and p.get("active", True)]
        pool = active or [p for p in prices if isinstance(p, dict)]
        if not pool:
            return None
        return max(pool, key=lambda p: clean(p.get("createdAt")))

    if isinstance(prices, dict):
        return prices

    return None


def iter_rows(raw_file: Path, market_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw = json.loads(raw_file.read_text(encoding="utf-8"))

    if not raw.get("ok", True) or int(raw.get("status") or 200) >= 400:
        return []

    fixture_id, team1, team2, start_time = fixture_team_names(raw)
    data = raw.get("data") or {}
    bookmakers = data.get("bookmakers") or {}

    rows: list[dict[str, Any]] = []

    for bookmaker, bookmaker_payload in bookmakers.items():
        markets = (bookmaker_payload or {}).get("markets") or {}

        for market_id, market_payload in markets.items():
            market_meta = market_by_id.get(clean(market_id))
            if not market_meta:
                continue

            normalized_market = mapped_market(market_meta)
            if not normalized_market:
                continue

            market_type = clean(market_meta.get("marketType"))
            market_name = clean(market_meta.get("marketName"))
            handicap = market_meta.get("handicap")

            outcomes = (market_payload or {}).get("outcomes") or {}
            for outcome_id, outcome_payload in outcomes.items():
                outcome_name = ""
                for outcome in market_meta.get("outcomes", []) or []:
                    if clean(outcome.get("outcomeId")) == clean(outcome_id):
                        outcome_name = clean(outcome.get("outcomeName"))
                        break

                player_map = (outcome_payload or {}).get("players") or {}

                # Non-player markets usually use player key "0".
                price_payload = latest_price(player_map.get("0"))
                if not price_payload:
                    # Be permissive if OddsPapi uses another singleton key.
                    for values in player_map.values():
                        price_payload = latest_price(values)
                        if price_payload:
                            break

                if not price_payload:
                    continue

                decimal_odds = to_float(price_payload.get("price"))
                american_odds = decimal_to_american(decimal_odds)

                side = ""
                team = ""
                opponent = ""
                line_value = handicap if handicap is not None else ""

                if outcome_name in {"Over", "Under"}:
                    side = outcome_name.lower()
                    team = team1
                    opponent = team2
                elif outcome_name == "1":
                    side = team1
                    team = team1
                    opponent = team2
                    # OddsPapi handicap markets store the handicap magnitude at the market level.
                    # Outcome 1 receives the positive side; outcome 2 receives the negative side.
                    if market_type.lower() == "spreads" and handicap is not None:
                        line_value = abs(float(handicap))
                elif outcome_name == "2":
                    side = team2
                    team = team2
                    opponent = team1
                    if market_type.lower() == "spreads" and handicap is not None:
                        line_value = -abs(float(handicap))
                else:
                    side = outcome_name

                rows.append(
                    {
                        "fixtureId": fixture_id,
                        "startTime": start_time,
                        "date": "",
                        "bookmaker": clean(bookmaker),
                        "market": normalized_market,
                        "team": team,
                        "opponent": opponent,
                        "line": line_value,
                        "marketId": clean(market_id),
                        "marketType": market_type,
                        "marketName": market_name,
                        "outcomeId": clean(outcome_id),
                        "outcomeName": outcome_name,
                        "side": side,
                        "decimalOdds": decimal_odds if decimal_odds is not None else "",
                        "americanOdds": american_odds if american_odds is not None else "",
                        "active": price_payload.get("active", True),
                        "createdAt": clean(price_payload.get("createdAt")),
                        "away": team2,
                        "home": team1,
                    }
                )

    return rows


def main() -> int:
    global ODDSPAPI_DIR

    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--raw-dir", default=str(ODDSPAPI_DIR))
    args = parser.parse_args()

    ODDSPAPI_DIR = Path(args.raw_dir)

    market_by_id, _ = load_markets()

    raw_files = sorted(ODDSPAPI_DIR.glob("historical_odds_id*_fanduel_draftkings_betmgm.json"))
    rows: list[dict[str, Any]] = []

    for raw_file in raw_files:
        rows.extend(iter_rows(raw_file, market_by_id))

    # Restrict to raw files written by the requested fixture candidate file when possible.
    fixture_file = ODDSPAPI_DIR / f"mlb_fixture_candidates_{args.from_date}_to_{args.to_date}.json"
    if fixture_file.exists():
        payload = json.loads(fixture_file.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            pool = payload
        elif isinstance(payload, dict):
            pool = payload.get("data", payload)
            if isinstance(pool, dict):
                pool = pool.get("fixtures", pool.get("items", []))
        else:
            pool = []

        fixture_ids = {
            clean(fx.get("fixtureId") or fx.get("id"))
            for fx in pool
            if isinstance(fx, dict)
        }
        fixture_ids.discard("")
        if fixture_ids:
            rows = [row for row in rows if row.get("fixtureId") in fixture_ids]

    for row in rows:
        row["date"] = args.from_date

    out = ODDSPAPI_DIR / f"historical_game_markets_pregame_latest_{args.from_date}_to_{args.to_date}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "fixtureId",
        "startTime",
        "date",
        "bookmaker",
        "market",
        "team",
        "opponent",
        "line",
        "marketId",
        "marketType",
        "marketName",
        "outcomeId",
        "outcomeName",
        "side",
        "decimalOdds",
        "americanOdds",
        "active",
        "createdAt",
        "away",
        "home",
    ]

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["market"]] = counts.get(row["market"], 0) + 1

    print("output:", out)
    print("rows:", len(rows))
    print("rows by market:")
    for market, count in sorted(counts.items()):
        print(f"  {market}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
