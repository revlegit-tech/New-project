from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase17_common import (  # noqa: E402
    AUDIT_DIR,
    CONTEXT_FIELDS,
    DEFAULT_MARKETS,
    FIELD_ALIASES,
    STRING_CONTEXT_FIELDS,
    atomic_write_json,
    canonical_team,
    feature_coverage,
    filter_rows,
    first_value,
    flatten_json_records,
    implied_probability_from_american,
    implied_runs_from_total_and_moneylines,
    moneyline_move,
    normalized_market,
    normalized_text,
    parse_float,
    playerboard_path,
    read_csv_rows,
    read_json,
    row_date,
    source_candidates,
    total_move,
    write_csv_rows,
)


def _record_source(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _load_context_records(date: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    sources: list[str] = []
    for path in source_candidates(date):
        loaded: list[dict[str, Any]] = []
        if path.suffix.lower() == ".csv":
            loaded = [dict(row) for row in read_csv_rows(path)]
        elif path.suffix.lower() == ".json":
            payload = read_json(path, default=None)
            loaded = flatten_json_records(payload)
        if not loaded:
            continue
        source = _record_source(path)
        sources.append(source)
        for row in loaded:
            item = dict(row)
            item["_source"] = source
            loaded_home = first_value(item, FIELD_ALIASES["home_team"])
            loaded_away = first_value(item, FIELD_ALIASES["away_team"])
            if not loaded_home or not loaded_away:
                game = first_value(item, FIELD_ALIASES["game"])
                if " @ " in game:
                    away, home = game.split(" @ ", 1)
                    item.setdefault("away_team", away)
                    item.setdefault("home_team", home)
                elif " vs " in game.lower():
                    left, right = game.lower().split(" vs ", 1)
                    item.setdefault("home_team", left)
                    item.setdefault("away_team", right)
            records.append(item)
    return records, sources


def _context_identity(record: dict[str, Any]) -> dict[str, str]:
    event_id = first_value(record, FIELD_ALIASES["event_id"])
    home = canonical_team(first_value(record, FIELD_ALIASES["home_team"]))
    away = canonical_team(first_value(record, FIELD_ALIASES["away_team"]))
    game = normalized_text(first_value(record, FIELD_ALIASES["game"]))
    return {"event_id": event_id, "home": home, "away": away, "game": game}


def _row_identity(row: dict[str, Any]) -> dict[str, str]:
    event_id = first_value(row, FIELD_ALIASES["event_id"])
    team = canonical_team(first_value(row, FIELD_ALIASES["team"] + FIELD_ALIASES["home_team"] + FIELD_ALIASES["away_team"]))
    opponent = canonical_team(first_value(row, FIELD_ALIASES["opponent"]))
    game = normalized_text(first_value(row, FIELD_ALIASES["game"]))
    return {"event_id": event_id, "team": team, "opponent": opponent, "game": game}


def match_context(row: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any] | None:
    row_id = _row_identity(row)
    if row_id["event_id"]:
        for record in records:
            context_id = _context_identity(record)
            if context_id["event_id"] and context_id["event_id"] == row_id["event_id"]:
                return record

    row_pair = {row_id["team"], row_id["opponent"]} - {""}
    for record in records:
        context_id = _context_identity(record)
        context_pair = {context_id["home"], context_id["away"]} - {""}
        if row_pair and row_pair == context_pair:
            return record

    if row_id["game"]:
        for record in records:
            context_id = _context_identity(record)
            game = context_id["game"]
            if game and (game == row_id["game"] or row_id["game"] in game or game in row_id["game"]):
                return record
    return None


def _side_for_row(row: dict[str, Any], context: dict[str, Any]) -> str:
    row_id = _row_identity(row)
    context_id = _context_identity(context)
    if row_id["team"] and row_id["team"] == context_id["home"]:
        return "home"
    if row_id["team"] and row_id["team"] == context_id["away"]:
        return "away"
    if row_id["opponent"] and row_id["opponent"] == context_id["away"]:
        return "home"
    if row_id["opponent"] and row_id["opponent"] == context_id["home"]:
        return "away"
    return ""


def _get_side_value(context: dict[str, Any], side: str, home_key: str, away_key: str) -> str:
    if side == "home":
        return first_value(context, FIELD_ALIASES[home_key])
    if side == "away":
        return first_value(context, FIELD_ALIASES[away_key])
    return ""


def apply_context(row: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], bool, list[str]]:
    updated = dict(row)
    changed = False
    fields_written: list[str] = []
    side = _side_for_row(row, context)
    opponent_side = "away" if side == "home" else "home" if side == "away" else ""

    def set_if_available(name: str, value: Any) -> None:
        nonlocal changed
        if value is None:
            return
        text = str(value).strip()
        if text == "":
            return
        if updated.get(name) != text:
            updated[name] = text
            changed = True
        fields_written.append(name)

    event_id = first_value(context, FIELD_ALIASES["event_id"])
    if event_id and not first_value(updated, FIELD_ALIASES["event_id"]):
        set_if_available("event_id", event_id)

    venue = first_value(context, FIELD_ALIASES["venue"])
    set_if_available("venue", venue)

    team_ml = _get_side_value(context, side, "home_moneyline", "away_moneyline")
    opp_ml = _get_side_value(context, opponent_side, "home_moneyline", "away_moneyline")
    open_team_ml = _get_side_value(context, side, "open_home_moneyline", "open_away_moneyline")
    open_opp_ml = _get_side_value(context, opponent_side, "open_home_moneyline", "open_away_moneyline")
    close_team_ml = _get_side_value(context, side, "close_home_moneyline", "close_away_moneyline") or team_ml
    close_opp_ml = _get_side_value(context, opponent_side, "close_home_moneyline", "close_away_moneyline") or opp_ml
    game_total = first_value(context, FIELD_ALIASES["game_total"])
    open_total = first_value(context, FIELD_ALIASES["open_game_total"])
    close_total = first_value(context, FIELD_ALIASES["close_game_total"]) or game_total

    set_if_available("team_moneyline", team_ml)
    set_if_available("opponent_moneyline", opp_ml)
    set_if_available("game_total", game_total)
    set_if_available("open_team_moneyline", open_team_ml)
    set_if_available("close_team_moneyline", close_team_ml)
    set_if_available("open_game_total", open_total)
    set_if_available("close_game_total", close_total)

    ml_move = moneyline_move(open_team_ml, close_team_ml)
    set_if_available("moneyline_move", ml_move)
    gt_move = total_move(open_total, close_total)
    set_if_available("total_move", gt_move)

    ml_prob = implied_probability_from_american(close_team_ml or team_ml)
    if ml_prob is not None:
        set_if_available("moneyline_implied_probability", round(ml_prob, 6))

    team_runs, opp_runs, implied_source = implied_runs_from_total_and_moneylines(close_team_ml or team_ml, close_opp_ml or opp_ml, close_total or game_total)
    set_if_available("team_implied_runs", team_runs)
    set_if_available("opponent_implied_runs", opp_runs)
    set_if_available("opponent_implied_runs_proxy", opp_runs)
    set_if_available("implied_runs_source", implied_source)

    set_if_available("park_factor", first_value(context, FIELD_ALIASES["park_factor"]))
    set_if_available("weather_temperature_f", first_value(context, FIELD_ALIASES["temperature"]))
    set_if_available("weather_wind_mph", first_value(context, FIELD_ALIASES["wind_speed"]))
    set_if_available("weather_wind_direction", first_value(context, FIELD_ALIASES["wind_direction"]))
    set_if_available("weather_humidity", first_value(context, FIELD_ALIASES["humidity"]))
    set_if_available("weather_precip_probability", first_value(context, FIELD_ALIASES["precip_probability"]))
    set_if_available("roof_status", first_value(context, FIELD_ALIASES["roof"]))
    set_if_available("game_context_source", context.get("_source"))
    return updated, changed, sorted(set(fields_written))


def enrich_rows(season: int, date: str, markets: list[str] | None = None, write: bool = True) -> dict[str, Any]:
    path = playerboard_path(season)
    rows = read_csv_rows(path)
    if not rows:
        return {"status": "missing_playerboard", "path": str(path), "updatedRows": 0, "matchedRows": 0}

    contexts, sources = _load_context_records(date)
    wanted = {normalized_market(market) for market in (markets or DEFAULT_MARKETS)}
    updated_rows: list[dict[str, Any]] = []
    changed_rows = 0
    matched_rows = 0
    missing_context = 0
    source_counts: dict[str, int] = defaultdict(int)
    fields_written: dict[str, int] = defaultdict(int)

    for row in rows:
        target = (not wanted or normalized_market(row) in wanted) and (not row_date(row) or row_date(row) == date)
        if not target:
            updated_rows.append(row)
            continue
        context = match_context(row, contexts)
        if not context:
            missing_context += 1
            updated_rows.append(row)
            continue
        matched_rows += 1
        updated, changed, fields = apply_context(row, context)
        if changed:
            changed_rows += 1
        for field in fields:
            fields_written[field] += 1
        source_counts[str(context.get("_source", "unknown"))] += 1
        updated_rows.append(updated)

    if write and updated_rows:
        write_csv_rows(path, updated_rows)

    audited = filter_rows(updated_rows, date=date)
    coverage = feature_coverage(audited, CONTEXT_FIELDS, string_fields=STRING_CONTEXT_FIELDS)
    payload = {
        "status": "ok",
        "date": date,
        "season": season,
        "path": str(path),
        "contextSources": sources,
        "contextRecords": len(contexts),
        "playerboardRows": len(rows),
        "matchedRows": matched_rows,
        "updatedRows": changed_rows,
        "missingContextRows": missing_context,
        "sourceCounts": dict(source_counts),
        "fieldsWritten": dict(fields_written),
        "coverage": coverage,
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(AUDIT_DIR / f"phase17_game_context_enrichment_{season}_{date}.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich live Playerboard rows with same-date game context, totals, weather, and park features.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    payload = enrich_rows(args.season, args.date, markets=args.markets, write=not args.dry_run)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
