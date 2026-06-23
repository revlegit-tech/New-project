from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mlb_app.services.actionnetwork_source_policy import resolve_collection_policy


ACTIONNETWORK_MARKETS: dict[str, dict[str, str]] = {
    "home_runs": {"label": "HRs", "slug": "home-runs"},
    "team_total": {"label": "Team Total", "slug": "team-total"},
    "batting": {"label": "Batting", "slug": "batting"},
    "runs_and_bases": {"label": "Runs & Bases", "slug": "runs-and-bases"},
    "pitching": {"label": "Pitching", "slug": "pitching"},
    "alt_home_runs": {"label": "Alt HRs", "slug": "alt-home-runs"},
    "alt_hits": {"label": "Alt Hits", "slug": "alt-hits"},
    "alt_strikeouts": {"label": "Alt Ks", "slug": "alt-strikeouts"},
    "alt_bases": {"label": "Alt Bases", "slug": "alt-bases"},
    "alt_runs": {"label": "Alt Runs", "slug": "alt-runs"},
    "alt_stolen_bases": {"label": "Alt SB", "slug": "alt-stolen-bases"},
}

BOOKS_URL = "https://api.actionnetwork.com/web/v1/books"


def normalize_date(value: str | None) -> tuple[str, str]:
    policy = resolve_collection_policy(value, allow_past_diagnostic=True)
    return policy.game_date, policy.yyyymmdd


def fetch_text(url: str, cache_path: Path, refresh: bool = False) -> str:
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists() and cache_path.stat().st_size > 0 and not refresh:
        return cache_path.read_text(encoding="utf-8", errors="ignore")

    req = Request(
        url,
        headers={
            "User-Agent": "revlegit-mlb-research/0.1",
            "Accept": "text/html,application/json,text/plain,*/*",
        },
    )

    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            cache_path.write_text(body, encoding="utf-8")
            return body
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error fetching {url}: {exc}") from exc


def american_to_implied_prob(odds: int | float | str | None) -> float | None:
    if odds is None or odds == "":
        return None

    try:
        odds_int = int(float(odds))
    except (TypeError, ValueError):
        return None

    if odds_int == 0:
        return None

    if odds_int > 0:
        return round(100 / (odds_int + 100), 6)

    return round(abs(odds_int) / (abs(odds_int) + 100), 6)


def extract_next_data(html: str) -> dict[str, Any]:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )

    if not match:
        raise RuntimeError("Could not find __NEXT_DATA__ in ActionNetwork HTML.")

    return json.loads(match.group(1))


def first_present(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and row[key] is not None and row[key] != "":
            return row[key]
    return None


def flatten_outcomes(obj: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def looks_like_outcome(value: dict[str, Any]) -> bool:
        required = {"outcome_id", "market_id", "event_id", "book_id"}
        has_required = required.issubset(value.keys())
        has_price = any(key in value for key in ["odds", "money", "american_odds"])
        has_market_type = any(key in value for key in ["type", "market_type"])
        return has_required and has_price and has_market_type

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if looks_like_outcome(value):
                rows.append(value)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(obj)
    return rows


def build_lookup(items: Any) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    if not isinstance(items, list):
        return lookup

    for item in items:
        if not isinstance(item, dict):
            continue

        item_id = item.get("id") or item.get("player_id") or item.get("team_id")
        if item_id is not None:
            lookup[str(item_id)] = item

    return lookup


def display_name(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None

    for key in ["full_name", "display_name", "name", "player_name"]:
        if item.get(key):
            return str(item[key])

    first = item.get("first_name") or item.get("firstName")
    last = item.get("last_name") or item.get("lastName")

    if first or last:
        return f"{first or ''} {last or ''}".strip()

    return None


def market_name(market_rules: dict[str, Any], market_type: str | None) -> str | None:
    if not market_type:
        return None

    rule = market_rules.get(market_type)
    if isinstance(rule, dict):
        return rule.get("name") or rule.get("full_name") or rule.get("display_name")

    return None


def build_option_lookup(market_rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    def maybe_add(option_id: Any, value: Any) -> None:
        if not isinstance(value, dict) or option_id is None:
            return

        option_type = value.get("option_type") or value.get("name") or value.get("display_name")
        if not option_type:
            return

        row = dict(value)
        row.setdefault("id", option_id)
        lookup[str(option_id)] = row

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            # ActionNetwork stores option ids as keys under rules.options:
            # {"54": {"option_type": "Over"}, "55": {"option_type": "Under"}}
            options = value.get("options")
            if isinstance(options, dict):
                for option_id, option in options.items():
                    maybe_add(option_id, option)

            option_id = value.get("id") or value.get("option_type_id")
            maybe_add(option_id, value)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(market_rules)
    return lookup


def option_label(option: dict[str, Any] | None) -> str | None:
    if not option:
        return None

    return (
        option.get("option_type")
        or option.get("name")
        or option.get("display_name")
        or option.get("label")
    )


def option_abbreviation(option: dict[str, Any] | None) -> str | None:
    if not option:
        return None

    return option.get("abbreviation") or option.get("abbr")


def canonical_bet_side(option: dict[str, Any] | None) -> str | None:
    label = option_label(option)
    if not label:
        return None

    normalized = str(label).strip().lower()

    if normalized in {"over", "yes"}:
        return "over_yes"

    if normalized in {"under", "no"}:
        return "under_no"

    return normalized.replace(" ", "_")


def walk_books(obj: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def walk(value: Any, path: str = "root") -> None:
        if isinstance(value, dict):
            keys = set(value.keys())
            has_book_shape = bool(
                keys
                & {
                    "display_name",
                    "source_name",
                    "parent_name",
                    "abbr",
                    "book_parent_id",
                    "book_id",
                    "website",
                    "deeplink",
                    "primary_color",
                    "secondary_color",
                }
            )
            has_id = any(key in value for key in ["id", "book_id"])

            if has_book_shape and has_id:
                row = dict(value)
                row["_path"] = path
                rows.append(row)

            for key, child in value.items():
                walk(child, f"{path}.{key}")

        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")

    walk(obj)
    return rows


def load_book_lookup(raw_dir: Path, yyyymmdd: str, refresh: bool = False) -> dict[str, dict[str, Any]]:
    path = raw_dir / f"actionnetwork_books_{yyyymmdd}.json"
    text = fetch_text(BOOKS_URL, path, refresh=refresh)
    data = json.loads(text)

    lookup: dict[str, dict[str, Any]] = {}

    for book in walk_books(data):
        book_id = book.get("id") or book.get("book_id")
        if book_id is not None:
            lookup[str(book_id)] = book

    return lookup


def build_initial_book_lookup(page_props: dict[str, Any]) -> dict[str, dict[str, Any]]:
    books = page_props.get("initialBooks", [])
    return build_lookup(books)


def resolve_book(
    book_id: Any,
    initial_books: dict[str, dict[str, Any]],
    global_books: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if book_id is None:
        return {}

    return global_books.get(str(book_id)) or initial_books.get(str(book_id)) or {}


def book_brand(book: dict[str, Any], book_id: Any, book_parent_id: Any) -> str:
    return (
        book.get("parent_name")
        or book.get("display_name")
        or book.get("source_name")
        or book.get("abbr")
        or f"book_{book_id}_parent_{book_parent_id}"
    )


def book_display_name(book: dict[str, Any], book_id: Any, book_parent_id: Any) -> str:
    return (
        book.get("display_name")
        or book.get("parent_name")
        or book.get("source_name")
        or book.get("abbr")
        or f"book_{book_id}_parent_{book_parent_id}"
    )


def parse_market_html(
    *,
    html: str,
    market_key: str,
    market_label: str,
    market_slug: str,
    game_date: str,
    source_html: Path,
    source_url: str,
    global_books: dict[str, dict[str, Any]],
    snapshot_id: str,
    collection_mode: str,
    exclude_from_ml: str,
    exclude_reason: str,
) -> list[dict[str, Any]]:
    data = extract_next_data(html)
    page_props = data.get("props", {}).get("pageProps", {})
    response = page_props.get("initialMarketConfig", {}).get("response", {})

    players = build_lookup(response.get("players", []))
    teams = build_lookup(response.get("teams", []))
    market_rules = response.get("market_rules", {}) or {}
    option_lookup = build_option_lookup(market_rules)
    initial_books = build_initial_book_lookup(page_props)

    outcomes = flatten_outcomes(response)
    snapshot_time = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for outcome in outcomes:
        market_type = first_present(outcome, ["type", "market_type"])
        odds = first_present(outcome, ["odds", "money", "american_odds"])
        line = first_present(outcome, ["value", "line"])
        option_type_id = outcome.get("option_type_id")
        option = option_lookup.get(str(option_type_id)) if option_type_id is not None else None

        book_id = outcome.get("book_id")
        book = resolve_book(book_id, initial_books, global_books)
        book_parent_id = outcome.get("book_parent_id") or book.get("book_parent_id") or book.get("parent_id")

        player_id = outcome.get("player_id")
        team_id = outcome.get("team_id")

        dedupe_key = (
            outcome.get("outcome_id"),
            outcome.get("market_id"),
            outcome.get("event_id"),
            book_id,
            player_id,
            team_id,
            market_type,
            option_type_id,
            line,
            odds,
        )

        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        rows.append(
            {
                "source": "actionnetwork",
                "sport": "mlb",
                "market_group": market_key,
                "market_group_label": market_label,
                "market_slug": market_slug,
                "market": market_name(market_rules, market_type) or market_label,
                "market_type": market_type,
                "option_type_id": option_type_id,
                "option_type": option_label(option),
                "option_abbreviation": option_abbreviation(option),
                "bet_side": canonical_bet_side(option),
                "game_date": game_date,
                "event_id": outcome.get("event_id"),
                "market_id": outcome.get("market_id"),
                "outcome_id": outcome.get("outcome_id"),
                "player_id": player_id,
                "player_name": display_name(players.get(str(player_id))) if player_id is not None else None,
                "team_id": team_id,
                "team_name": display_name(teams.get(str(team_id))) if team_id is not None else None,
                "book_id": book_id,
                "book_parent_id": book_parent_id,
                "book": book_brand(book, book_id, book_parent_id),
                "book_display_name": book_display_name(book, book_id, book_parent_id),
                "book_parent_name": book.get("parent_name"),
                "book_source_name": book.get("source_name"),
                "book_abbr": book.get("abbr"),
                "line": line,
                "american_odds": odds,
                "implied_probability": american_to_implied_prob(odds),
                "is_best": outcome.get("is_best"),
                "is_live": outcome.get("is_live"),
                "line_status": outcome.get("line_status"),
                "deeplink_id": outcome.get("deeplink_id"),
                "snapshot_time": snapshot_time,
                "snapshot_id": snapshot_id,
                "collection_mode": collection_mode,
                "exclude_from_ml": exclude_from_ml,
                "exclude_reason": exclude_reason,
                "source_html": str(source_html),
                "source_url": source_url,
            }
        )

    return rows


def resolve_markets(value: str) -> dict[str, dict[str, str]]:
    if value == "all":
        return ACTIONNETWORK_MARKETS

    selected: dict[str, dict[str, str]] = {}

    for token in value.split(","):
        token = token.strip()
        if not token:
            continue

        if token in ACTIONNETWORK_MARKETS:
            selected[token] = ACTIONNETWORK_MARKETS[token]
            continue

        slug_match = {
            key: spec
            for key, spec in ACTIONNETWORK_MARKETS.items()
            if spec["slug"] == token
        }

        if slug_match:
            selected.update(slug_match)
            continue

        valid = ", ".join(ACTIONNETWORK_MARKETS.keys())
        raise ValueError(f"Unknown market '{token}'. Valid keys: {valid}")

    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect public ActionNetwork MLB prop odds.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD or YYYYMMDD. Defaults to today.")
    parser.add_argument("--market", default="all", help="all, a market key, a slug, or comma-separated values.")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached raw HTML/book JSON.")
    parser.add_argument("--sleep", type=float, default=0.4, help="Delay between market page requests.")
    parser.add_argument(
        "--allow-past-diagnostic",
        action="store_true",
        help="Allow past-date diagnostic collection. Rows are excluded from ML.",
    )

    args = parser.parse_args()

    policy = resolve_collection_policy(args.date, allow_past_diagnostic=args.allow_past_diagnostic)
    if policy.warning:
        print(policy.warning)
    game_date, yyyymmdd = policy.game_date, policy.yyyymmdd

    raw_dir = Path("data/warehouse/raw/actionnetwork")
    raw_pages_dir = raw_dir / "pages"
    out_dir = Path("data/warehouse/normalized/odds")
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_stamp = datetime.now().strftime("%H%M%S")
    snapshot_id = f"{game_date}_{snapshot_stamp}"
    snapshot_pages_dir = raw_pages_dir / "snapshots" / game_date / snapshot_stamp

    selected_markets = resolve_markets(args.market)
    global_books = load_book_lookup(raw_dir, yyyymmdd, refresh=args.refresh)

    all_rows: list[dict[str, Any]] = []

    for market_key, spec in selected_markets.items():
        slug = spec["slug"]
        label = spec["label"]
        source_url = f"https://www.actionnetwork.com/mlb/props/{slug}?date={yyyymmdd}"

        safe_slug = slug.replace("-", "_")
        html_path = snapshot_pages_dir / f"actionnetwork_{safe_slug}_{yyyymmdd}_{snapshot_stamp}.html"

        print(f"fetching {market_key}: {source_url}")
        html = fetch_text(source_url, html_path, refresh=args.refresh)

        rows = parse_market_html(
            html=html,
            market_key=market_key,
            market_label=label,
            market_slug=slug,
            game_date=game_date,
            source_html=html_path,
            source_url=source_url,
            global_books=global_books,
            snapshot_id=snapshot_id,
            collection_mode=policy.collection_mode,
            exclude_from_ml=policy.exclude_from_ml,
            exclude_reason=policy.exclude_reason,
        )

        print(f"  rows={len(rows)} raw={html_path}")
        all_rows.extend(rows)

        if args.sleep:
            time.sleep(args.sleep)

    out_path = out_dir / f"actionnetwork_all_markets_{game_date}.csv"
    snapshot_out_path = out_dir / f"actionnetwork_all_markets_{game_date}_{snapshot_stamp}.csv"

    fieldnames = [
        "source",
        "sport",
        "market_group",
        "market_group_label",
        "market_slug",
        "market",
        "market_type",
        "option_type_id",
        "option_type",
        "option_abbreviation",
        "bet_side",
        "game_date",
        "event_id",
        "market_id",
        "outcome_id",
        "player_id",
        "player_name",
        "team_id",
        "team_name",
        "book_id",
        "book_parent_id",
        "book",
        "book_display_name",
        "book_parent_name",
        "book_source_name",
        "book_abbr",
        "line",
        "american_odds",
        "implied_probability",
        "is_best",
        "is_live",
        "line_status",
        "deeplink_id",
        "snapshot_time",
        "snapshot_id",
        "collection_mode",
        "exclude_from_ml",
        "exclude_reason",
        "source_html",
        "source_url",
    ]

    def write_csv(path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_rows)

    write_csv(out_path)
    write_csv(snapshot_out_path)

    print("")
    print(f"saved_csv={out_path}")
    print(f"saved_snapshot_csv={snapshot_out_path}")
    print(f"snapshot_raw_dir={snapshot_pages_dir}")
    print(f"total_rows={len(all_rows)}")

    counts: dict[str, int] = {}
    for row in all_rows:
        key = str(row["market_group"])
        counts[key] = counts.get(key, 0) + 1

    print("")
    print("rows_by_market:")
    for key, count in sorted(counts.items()):
        print(f"  {key}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
