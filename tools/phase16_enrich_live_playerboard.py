from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase16_common import (
    DEFAULT_MARKETS,
    FIELD_ALIASES,
    atomic_write_json,
    best_book_price,
    feature_coverage,
    filter_rows,
    first_value,
    implied_probability_from_american,
    match_key,
    normalized_market,
    parse_float,
    playerboard_path,
    propline_path,
    read_csv_rows,
    row_date,
    write_csv_rows,
    AUDIT_DIR,
)


def _load_books_from_board(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("books") or row.get("sportsbooks") or ""
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    books = []
    for item in payload:
        if isinstance(item, dict):
            books.append(item)
    return books


def _index_propline(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = match_key(row)
        index[key].append(row)
        # Also index player/market/line without direction as Over for sources that omit side.
        fallback = (key[0], key[1], key[2], "over")
        if fallback != key:
            index[fallback].append(row)
    return index


def enrich_rows(season: int, date: str, markets: list[str] | None = None) -> dict[str, Any]:
    path = playerboard_path(season)
    rows = read_csv_rows(path)
    if not rows:
        return {"status": "missing_playerboard", "path": str(path), "updatedRows": 0}

    propline_rows = read_csv_rows(propline_path(date))
    propline_index = _index_propline(propline_rows)
    wanted = {normalized_market(market) for market in (markets or DEFAULT_MARKETS)}

    updated = []
    untouched = []
    changed = 0
    matched = 0
    missing_propline = 0
    feature_sources = defaultdict(int)

    for row in rows:
        market = normalized_market(row)
        slate_date = row_date(row)
        if market not in wanted or (slate_date and slate_date != date):
            untouched.append(row)
            updated.append(row)
            continue

        out = dict(row)
        key = match_key(out)
        source_rows = propline_index.get(key, [])
        if not source_rows:
            # Try a direction-agnostic match. This protects old board rows that lost rawLabel.
            no_side = (key[0], key[1], key[2], "over")
            source_rows = propline_index.get(no_side, [])
        if source_rows:
            matched += 1
        else:
            missing_propline += 1

        # Merge board books and PropLine books, preserving the ladder in one card.
        book_rows = list(source_rows)
        for book in _load_books_from_board(out):
            book_rows.append(book)
        best_odds, best_book, books = best_book_price(book_rows)

        before = dict(out)
        if best_odds is not None:
            out["american_odds"] = str(best_odds)
            out["best_american_odds"] = str(best_odds)
            out["sportsbook_implied_probability"] = f"{(implied_probability_from_american(best_odds) or 0):.6f}"
            feature_sources["propline_books"] += 1
        if best_book:
            out["best_book"] = best_book
        if books:
            out["sportsbook_count"] = str(len({item.get("book", "") for item in books if item.get("book")}))
            out["books"] = json.dumps(books, ensure_ascii=False, separators=(",", ":"))
        event_id = first_value(source_rows[0], FIELD_ALIASES["event_id"]) if source_rows else ""
        if event_id:
            out["event_id"] = event_id

        # Preserve existing real game context if already available. Do not invent it.
        team_ml = first_value(out, ["team_moneyline", "close_team_moneyline"])
        opp_ml = first_value(out, ["opponent_moneyline"])
        game_total = first_value(out, ["game_total", "close_game_total"])
        if team_ml:
            out["moneyline_implied_probability"] = f"{(implied_probability_from_american(team_ml) or 0):.6f}"
        if parse_float(out.get("close_team_moneyline")) is not None and parse_float(out.get("open_team_moneyline")) is not None:
            out["moneyline_move"] = f"{parse_float(out['close_team_moneyline']) - parse_float(out['open_team_moneyline']):.3f}"
        if parse_float(out.get("close_game_total")) is not None and parse_float(out.get("open_game_total")) is not None:
            out["total_move"] = f"{parse_float(out['close_game_total']) - parse_float(out['open_game_total']):.3f}"

        # Derived implied-runs features only when real moneyline/total inputs exist.
        if parse_float(team_ml) is not None and parse_float(opp_ml) is not None and parse_float(game_total) is not None:
            total = parse_float(game_total) or 0.0
            team_prob = implied_probability_from_american(team_ml) or 0.5
            opp_prob = implied_probability_from_american(opp_ml) or 0.5
            denom = max(0.0001, team_prob + opp_prob)
            team_share = team_prob / denom
            team_runs = total * team_share
            opp_runs = total - team_runs
            out["team_implied_runs"] = f"{team_runs:.3f}"
            out["opponent_implied_runs"] = f"{opp_runs:.3f}"
            out["opponent_implied_runs_proxy"] = f"{opp_runs:.3f}"

        missing_live = []
        for field in [
            "american_odds",
            "event_id",
            "team_moneyline",
            "opponent_moneyline",
            "game_total",
            "moneyline_implied_probability",
            "team_implied_runs",
            "opponent_implied_runs",
            "park_factor",
        ]:
            if str(out.get(field, "")).strip() == "":
                missing_live.append(field)
        out["liveFeatureMissing"] = json.dumps(missing_live, separators=(",", ":"))
        out["liveFeatureStatus"] = "ok" if not missing_live else "partial"
        out["liveFeatureSource"] = "propline+existing_context" if source_rows else "existing_context_only"

        if out != before:
            changed += 1
        updated.append(out)

    if changed:
        write_csv_rows(path, updated)

    report = {
        "status": "ok",
        "date": date,
        "season": season,
        "path": str(path),
        "proplinePath": str(propline_path(date)),
        "playerboardRows": len(rows),
        "proplineRows": len(propline_rows),
        "matchedRows": matched,
        "missingProplineRows": missing_propline,
        "updatedRows": changed,
        "sourceCounts": dict(feature_sources),
    }
    atomic_write_json(AUDIT_DIR / f"phase16_live_feature_enrichment_{date}.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich live Playerboard rows with real same-date PropLine/live features.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    args = parser.parse_args()
    print(json.dumps(enrich_rows(args.season, args.date, args.markets), indent=2))


if __name__ == "__main__":
    main()
