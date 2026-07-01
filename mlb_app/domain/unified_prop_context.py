from __future__ import annotations

"""All Data Prop Predictor.

This is the non-ML prediction layer. It uses all available synced data:
- PropLine odds/current prop context
- MLB StatsAPI schedule/results warehouse
- Open-Meteo weather summaries
- Savant/pybaseball quality metrics
- Batter-vs-pitcher summaries derived from Statcast
- Self-stored odds snapshots for future line movement

It is intentionally transparent: it returns probability, edge, confidence,
data used, missing data, and adjustment breakdown.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
SUMMARY_DIR = WAREHOUSE_DIR / "summaries"
CLOUD_SUMMARY_DIR = DATA_DIR / "cloud" / "summaries"
EXTERNAL_DIR = WAREHOUSE_DIR / "external"
SAVANT_DIR = EXTERNAL_DIR / "savant"
CHADWICK_DIR = EXTERNAL_DIR / "chadwick"
ODDS_SNAPSHOT_DIR = WAREHOUSE_DIR / "odds_snapshots"
_CSV_CACHE: dict[tuple[str, int, int], list[dict[str, str]]] = {}
_JSON_CACHE: dict[tuple[str, int, int], Any] = {}
_CHADWICK_LOOKUP_CACHE: dict[tuple[str, int, int], dict[str, str]] = {}

TEAM_GAME_MARKETS = {
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

SUPPORTED_MARKETS = {
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
    "batter_hits_alt",
    "batter_total_bases_alt",
    "batter_home_runs_alt",
    "pitcher_strikeouts_alt",
    "pitcher_hits_allowed_alt",
    "pitcher_earned_runs_alt",
    *TEAM_GAME_MARKETS,
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def pct(value: float) -> float:
    return round(value * 100.0, 2)


def clamp(value: float, low: float = 0.01, high: float = 0.99) -> float:
    return max(low, min(high, value))


def implied_probability_from_american(odds: float | None) -> float | None:
    if odds is None:
        return None
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return None


def american_from_probability(probability: float) -> int:
    probability = clamp(probability, 0.001, 0.999)
    if probability >= 0.5:
        return round(-100 * probability / (1 - probability))
    return round(100 * (1 - probability) / probability)



def base_market(market: Any) -> str:
    text = clean(market)
    return text[:-4] if text.endswith("_alt") else text


def is_alt_market(market: Any) -> bool:
    return clean(market).endswith("_alt")



def market_label(market: str) -> str:
    label = market.replace("_alt", " Alt").replace("_", " ").title()
    return label


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if key in _JSON_CACHE:
        return _JSON_CACHE[key]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        _JSON_CACHE[key] = payload
        return payload
    except Exception:
        return default


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _CSV_CACHE.get(key)
    if cached is not None:
        return cached
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _CSV_CACHE[key] = rows
    return rows


def find_latest_file(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.glob(pattern), reverse=True)
    return files[0] if files else None


def normalize_name(value: str) -> str:
    return " ".join(clean(value).lower().replace(".", "").replace(",", "").split())


def load_chadwick_crosswalk() -> dict[str, str]:
    path = CHADWICK_DIR / "mlbam_crosswalk.csv"
    if not path.exists():
        return {}
    stat = path.stat()
    cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _CHADWICK_LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    lookup: dict[str, str] = {}

    try:
        for row in load_csv_rows(path):
            first = clean(row.get("name_first"))
            last = clean(row.get("name_last"))
            given = clean(row.get("name_given"))
            mlbam = clean(row.get("key_mlbam"))
            if not mlbam:
                continue

            for name in [f"{first} {last}", given]:
                key = normalize_name(name)
                if key:
                    lookup[key] = mlbam
    except Exception:
        return lookup

    _CHADWICK_LOOKUP_CACHE[cache_key] = lookup
    return lookup


def player_to_mlbam(name: str) -> str:
    lookup = load_chadwick_crosswalk()
    return lookup.get(normalize_name(name), "")


def load_weather_context(date_label: str, team: str) -> dict[str, Any]:
    path = SUMMARY_DIR / f"weather_summary_{date_label}.json"
    rows = load_json(path, [])

    for row in rows:
        if clean(row.get("team")).upper() == clean(team).upper():
            return row

    return {}


def load_games_context(date_label: str, team: str, opponent: str) -> dict[str, Any]:
    paths = [
        SUMMARY_DIR / f"games_{date_label}.json",
        CLOUD_SUMMARY_DIR / f"games_{date_label}.json",
    ]

    team = clean(team).upper()
    opponent = clean(opponent).upper()

    for path in paths:
        rows = load_json(path, [])
        for row in rows:
            home = clean(row.get("home")).upper()
            away = clean(row.get("away")).upper()
            if {home, away} == {team, opponent}:
                return row

    return {}


def load_game_odds_context(date_label: str, team: str, opponent: str) -> dict[str, Any]:
    path = DATA_DIR / "imports" / f"game_odds_template_{date_label}.csv"
    if not path.exists():
        return {}

    team = clean(team).upper()
    opponent = clean(opponent).upper()

    try:
        for row in load_csv_rows(path):
            if clean(row.get("team")).upper() == team and clean(row.get("opponent")).upper() == opponent:
                return row
    except Exception:
        return {}

    return {}


def load_savant_quality(player_name: str, role: str = "batter") -> dict[str, Any]:
    """Look up most recent Savant summary using Chadwick MLBAM ID."""
    mlbam = player_to_mlbam(player_name)
    if not mlbam:
        return {}

    pattern = "batter_quality_*.csv" if role == "batter" else "pitcher_quality_*.csv"
    id_col = "batter_id" if role == "batter" else "pitcher_id"

    for path in sorted(SAVANT_DIR.glob(pattern), reverse=True):
        try:
            for row in load_csv_rows(path):
                if clean(row.get(id_col)) == mlbam:
                    out = dict(row)
                    out["_source"] = str(path)
                    out["_mlbam"] = mlbam
                    return out
        except Exception:
            continue

    return {}


def build_batter_pitcher_samples() -> dict[str, Any]:
    """Build batter-vs-pitcher summary from latest raw Statcast CSV."""
    raw = find_latest_file(SAVANT_DIR, "statcast_*.csv")
    if not raw:
        return {
            "available": False,
            "reason": "No Statcast raw CSV found. Run External Sources sync first.",
        }

    out_path = SAVANT_DIR / "batter_pitcher_samples.csv"
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    try:
        with raw.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)

            for row in reader:
                batter = clean(row.get("batter"))
                pitcher = clean(row.get("pitcher"))
                if not batter or not pitcher:
                    continue

                key = (batter, pitcher)
                item = groups.setdefault(key, {
                    "batter_id": batter,
                    "pitcher_id": pitcher,
                    "pitches": 0,
                    "pa_events": 0,
                    "hits": 0,
                    "home_runs": 0,
                    "strikeouts": 0,
                    "total_bases": 0,
                    "batted_balls": 0,
                    "ev_sum": 0.0,
                    "xwoba_sum": 0.0,
                    "xwoba_count": 0,
                })

                item["pitches"] += 1

                event = clean(row.get("events")).lower()
                if event:
                    item["pa_events"] += 1

                if event in {"single", "double", "triple", "home_run"}:
                    item["hits"] += 1

                if event == "home_run":
                    item["home_runs"] += 1

                if "strikeout" in event:
                    item["strikeouts"] += 1

                if event == "single":
                    item["total_bases"] += 1
                elif event == "double":
                    item["total_bases"] += 2
                elif event == "triple":
                    item["total_bases"] += 3
                elif event == "home_run":
                    item["total_bases"] += 4

                ev = to_float(row.get("launch_speed"), math.nan)
                if not math.isnan(ev):
                    item["batted_balls"] += 1
                    item["ev_sum"] += ev

                xwoba = to_float(row.get("estimated_woba_using_speedangle"), math.nan)
                if not math.isnan(xwoba):
                    item["xwoba_sum"] += xwoba
                    item["xwoba_count"] += 1

    except Exception as error:
        return {
            "available": False,
            "reason": str(error),
            "source": str(raw),
        }

    fieldnames = [
        "batter_id",
        "pitcher_id",
        "pitches",
        "pa_events",
        "hits",
        "home_runs",
        "strikeouts",
        "total_bases",
        "hit_rate",
        "hr_rate",
        "k_rate",
        "tb_per_pa",
        "avg_ev",
        "xwoba",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for item in groups.values():
            pa = max(int(item["pa_events"]), 1)
            bbe = max(int(item["batted_balls"]), 1)
            xcount = max(int(item["xwoba_count"]), 1)

            writer.writerow({
                "batter_id": item["batter_id"],
                "pitcher_id": item["pitcher_id"],
                "pitches": item["pitches"],
                "pa_events": item["pa_events"],
                "hits": item["hits"],
                "home_runs": item["home_runs"],
                "strikeouts": item["strikeouts"],
                "total_bases": item["total_bases"],
                "hit_rate": round(item["hits"] / pa, 4),
                "hr_rate": round(item["home_runs"] / pa, 4),
                "k_rate": round(item["strikeouts"] / pa, 4),
                "tb_per_pa": round(item["total_bases"] / pa, 4),
                "avg_ev": round(item["ev_sum"] / bbe, 3) if item["batted_balls"] else "",
                "xwoba": round(item["xwoba_sum"] / xcount, 4) if item["xwoba_count"] else "",
            })

    summary = {
        "available": True,
        "source": str(raw),
        "output": str(out_path),
        "matchups": len(groups),
    }

    summary_path = SUMMARY_DIR / "batter_pitcher_samples_status.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


def load_batter_pitcher_context(batter_name: str, pitcher_name: str) -> dict[str, Any]:
    batter_id = player_to_mlbam(batter_name)
    pitcher_id = player_to_mlbam(pitcher_name)

    if not batter_id or not pitcher_id:
        return {}

    path = SAVANT_DIR / "batter_pitcher_samples.csv"
    if not path.exists():
        build_batter_pitcher_samples()

    if not path.exists():
        return {}

    try:
        for row in load_csv_rows(path):
            if clean(row.get("batter_id")) == batter_id and clean(row.get("pitcher_id")) == pitcher_id:
                out = dict(row)
                out["_batter_id"] = batter_id
                out["_pitcher_id"] = pitcher_id
                return out
    except Exception:
        return {}

    return {}


def odds_snapshot_context(date_label: str, player: str, market: str) -> dict[str, Any]:
    snapshots = sorted(ODDS_SNAPSHOT_DIR.glob(f"propline_props_{date_label}_*.csv"))

    if len(snapshots) < 2:
        return {
            "snapshots": len(snapshots),
            "movementAvailable": False,
        }

    def find_price(path: Path) -> float:
        try:
            for row in load_csv_rows(path):
                if normalize_name(row.get("player", "")) == normalize_name(player) and clean(row.get("market")) == market:
                    return to_float(row.get("americanOdds") or row.get("american_odds"))
        except Exception:
            return 0.0
        return 0.0

    open_price = find_price(snapshots[0])
    close_price = find_price(snapshots[-1])

    return {
        "snapshots": len(snapshots),
        "movementAvailable": bool(open_price and close_price),
        "openOdds": open_price,
        "latestOdds": close_price,
        "oddsMove": round(close_price - open_price, 2) if open_price and close_price else 0,
    }


def baseline_probability(market: str, line: float, odds: float | None) -> float:
    implied = implied_probability_from_american(odds)

    # Start from market, not pure sportsbook. This prevents model from only copying odds.
    defaults = {
        "batter_hits": 0.56,
        "batter_total_bases": 0.47,
        "batter_home_runs": 0.12,
        "pitcher_strikeouts": 0.50,
        "pitcher_hits_allowed": 0.50,
        "pitcher_earned_runs": 0.50,
        "moneyline": 0.50,
        "moneyline_first_five": 0.50,
        "run_line": 0.50,
        "run_line_first_five": 0.50,
        "run_line_first_inning": 0.50,
        "game_total_runs": 0.50,
        "first_five_total_runs": 0.50,
        "first_inning_total_runs": 0.50,
        "team_total_runs": 0.50,
        "team_first_to_score": 0.50,
    }

    base = defaults.get(market, 0.50)

    if implied is None:
        return clamp(base)

    # Blend with sportsbook implied because price contains useful market info.
    return clamp(base * 0.60 + implied * 0.40)


def all_data_predict(row: dict[str, Any]) -> dict[str, Any]:
    market = clean(row.get("market") or "batter_hits")
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}")
    model_market = base_market(market)

    player = clean(row.get("player"))
    team = clean(row.get("team")).upper()
    opponent = clean(row.get("opponent")).upper()
    pitcher = clean(row.get("pitcher"))
    date_label = clean(row.get("date"))
    line = to_float(row.get("line"), 0.5)
    odds_text = clean(row.get("american_odds") or row.get("americanOdds"))
    odds = to_float(odds_text, 0.0) if odds_text else None

    probability = baseline_probability(model_market, line, odds)
    implied = implied_probability_from_american(odds)

    data_used: list[str] = []
    missing: list[str] = []
    adjustments: list[dict[str, Any]] = []

    def apply_adjustment(name: str, amount: float, reason: str) -> None:
        nonlocal probability
        probability = clamp(probability + amount)
        adjustments.append({
            "name": name,
            "amount": round(amount, 4),
            "amountPercent": pct(amount),
            "reason": reason,
        })

    if odds is not None:
        data_used.append("Sportsbook implied probability from PropLine/user odds")
    else:
        missing.append("Sportsbook odds")

    game = load_games_context(date_label, team, opponent) if date_label else {}
    if game:
        data_used.append("MLB StatsAPI schedule/game context")
        if game.get("home") == team:
            apply_adjustment("Home field", 0.015, "Team is home")
        else:
            apply_adjustment("Away game", -0.005, "Team is away")
    else:
        missing.append("MLB schedule/game context")

    game_odds = load_game_odds_context(date_label, team, opponent) if date_label else {}
    if game_odds:
        data_used.append("PropLine game odds context")
        status = clean(game_odds.get("favorite_status"))
        total = to_float(game_odds.get("game_total"))
        opponent_runs = to_float(game_odds.get("opponent_implied_runs_proxy"))

        if status == "favorite" and (model_market.startswith("batter") or model_market in {"moneyline", "run_line", "moneyline_first_five", "run_line_first_five"}):
            apply_adjustment("Favorite status", 0.015, "Team is favored")
        elif status == "underdog" and (model_market.startswith("batter") or model_market in {"moneyline", "run_line", "moneyline_first_five", "run_line_first_five"}):
            apply_adjustment("Underdog status", -0.01, "Team is underdog")

        if total >= 9 and model_market in {"batter_hits", "batter_total_bases", "batter_home_runs", "game_total_runs", "team_total_runs", "first_inning_total_runs", "first_five_total_runs"}:
            apply_adjustment("High total", 0.025, f"Game total is {total}")
        elif total and total <= 7 and model_market in {"batter_hits", "batter_total_bases", "batter_home_runs", "game_total_runs", "team_total_runs", "first_inning_total_runs", "first_five_total_runs"}:
            apply_adjustment("Low total", -0.02, f"Game total is {total}")

        if opponent_runs >= 4.8 and model_market in {"pitcher_strikeouts", "pitcher_hits_allowed", "pitcher_earned_runs"}:
            apply_adjustment("Opponent implied runs", -0.02, f"Opponent implied runs proxy is {opponent_runs}")
    else:
        missing.append("PropLine game moneyline/total context")

    weather = load_weather_context(date_label, team) if date_label else {}
    if weather:
        data_used.append("Open-Meteo stadium weather")
        wind = to_float(weather.get("avgWindMph"))
        temp = to_float(weather.get("avgTempF"))

        if model_market == "batter_home_runs":
            if temp >= 78:
                apply_adjustment("Warm weather", 0.01, f"Average temperature is {temp}F")
            if wind >= 12:
                apply_adjustment("Wind impact", 0.005, f"Average wind is {wind} mph")
    else:
        missing.append("Open-Meteo weather context")

    role = "team" if model_market in TEAM_GAME_MARKETS else "pitcher" if model_market.startswith("pitcher") else "batter"
    savant = {} if role == "team" else load_savant_quality(player, role=role)
    if savant:
        data_used.append("Baseball Savant quality metrics")
        if role == "batter":
            hard_hit = to_float(savant.get("hard_hit_rate"))
            xwoba = to_float(savant.get("xwoba"))
            xslg = to_float(savant.get("xslg"))

            if hard_hit >= 0.42 and model_market in {"batter_hits", "batter_total_bases", "batter_home_runs"}:
                apply_adjustment("Hard-hit profile", 0.02, f"Hard-hit rate is {hard_hit}")
            if xwoba >= 0.360 and market in {"batter_hits", "batter_total_bases"}:
                apply_adjustment("xwOBA profile", 0.015, f"xwOBA is {xwoba}")
            if xslg >= 0.480 and market in {"batter_total_bases", "batter_home_runs"}:
                apply_adjustment("xSLG profile", 0.015, f"xSLG is {xslg}")
        else:
            whiff = to_float(savant.get("whiff_rate_proxy"))
            hard_allowed = to_float(savant.get("hard_hit_allowed_rate"))
            if whiff >= 0.13 and model_market == "pitcher_strikeouts":
                apply_adjustment("Whiff profile", 0.025, f"Whiff proxy is {whiff}")
            if hard_allowed >= 0.42 and market in {"pitcher_hits_allowed", "pitcher_earned_runs"}:
                apply_adjustment("Hard contact allowed", 0.02, f"Hard-hit allowed is {hard_allowed}")
    else:
        if role != "team":
            missing.append("Baseball Savant quality metrics")

    if pitcher and role == "batter":
        bvp = load_batter_pitcher_context(player, pitcher)
        if bvp:
            pa = int(to_float(bvp.get("pa_events")))
            data_used.append("Batter-vs-pitcher Statcast sample")
            if pa >= 5:
                if model_market == "batter_hits":
                    hit_rate = to_float(bvp.get("hit_rate"))
                    apply_adjustment("BvP hit sample", (hit_rate - 0.25) * 0.08, f"BvP hit rate {hit_rate} over {pa} PA events")
                elif model_market == "batter_total_bases":
                    tbpa = to_float(bvp.get("tb_per_pa"))
                    apply_adjustment("BvP total bases sample", (tbpa - 0.45) * 0.05, f"BvP TB/PA {tbpa} over {pa} PA events")
                elif model_market == "batter_home_runs":
                    hr_rate = to_float(bvp.get("hr_rate"))
                    apply_adjustment("BvP HR sample", (hr_rate - 0.04) * 0.08, f"BvP HR rate {hr_rate} over {pa} PA events")
            else:
                missing.append("Batter-vs-pitcher sample is too small")
        else:
            missing.append("Batter-vs-pitcher sample")
    elif role == "batter":
        missing.append("Pitcher name needed for batter-vs-pitcher sample")

    movement = odds_snapshot_context(date_label, player, market) if date_label and player else {}
    if movement.get("movementAvailable"):
        data_used.append("Self-stored odds line movement")
        move = to_float(movement.get("oddsMove"))
        # Positive American odds move usually means longer price, negative means shorter.
        if move < -15:
            apply_adjustment("Market movement", 0.01, f"Odds shortened by {move}")
        elif move > 15:
            apply_adjustment("Market movement", -0.01, f"Odds drifted by {move}")
    else:
        missing.append("Self-stored odds movement snapshots")

    edge = probability - implied if implied is not None else None

    used_count = len(data_used)
    if edge is not None and used_count >= 6 and abs(edge) >= 0.04:
        confidence = "Medium"
    elif used_count >= 4:
        confidence = "Low-Medium"
    else:
        confidence = "Low"

    if edge is None:
        recommendation = "Odds unavailable"
    elif edge >= 0.04 and confidence != "Low":
        recommendation = "Lean over / positive edge"
    elif edge <= -0.04:
        recommendation = "Avoid / negative edge"
    else:
        recommendation = "No clear edge"

    return {
        "market": market,
        "baseMarket": model_market,
        "isAltMarket": is_alt_market(market),
        "marketLabel": market_label(market),
        "player": player,
        "team": team,
        "opponent": opponent,
        "pitcher": pitcher,
        "date": date_label,
        "line": line,
        "americanOdds": odds,
        "probability": probability,
        "probabilityPercent": pct(probability),
        "sportsbookImpliedProbability": implied,
        "sportsbookImpliedPercent": pct(implied) if implied is not None else None,
        "edge": edge,
        "edgePercent": pct(edge) if edge is not None else None,
        "fairOdds": american_from_probability(probability),
        "confidence": confidence,
        "recommendation": recommendation,
        "dataUsed": data_used,
        "missingData": missing,
        "adjustments": adjustments,
        "contexts": {
            "game": game,
            "gameOdds": game_odds,
            "weather": weather,
            "savant": savant,
            "oddsMovement": movement,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run All Data Prop Predictor.")
    parser.add_argument("--json", required=True)
    parser.add_argument("--build-bvp", action="store_true")
    args = parser.parse_args()

    if args.build_bvp:
        print(json.dumps(build_batter_pitcher_samples(), indent=2))
        return

    print(json.dumps(all_data_predict(json.loads(args.json)), indent=2))


if __name__ == "__main__":
    main()
