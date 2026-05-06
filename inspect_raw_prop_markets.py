from collections import Counter
from pathlib import Path
import csv

import playerboard

date_label = "2026-05-05"

raw_market_counts = Counter()
normalized_market_counts = Counter()
kept_counts = Counter()
rejected_market_counts = Counter()
rejected_plausibility_counts = Counter()
possible_rows = []

market_set = {playerboard.normalize_market(m) for m in playerboard.DEFAULT_MARKETS}

raw_market_keys = [
    "market", "prop_market", "market_key", "marketKey", "type", "target",
    "stat", "category", "bet_type", "betType", "propType", "prop_type"
]

print("=" * 100)
print("DEFAULT_MARKETS")
for market in playerboard.DEFAULT_MARKETS:
    print(market)

print("\n" + "=" * 100)
print("SOURCE FILES")
files = playerboard.saved_prop_files(date_label)
for path in files:
    print(path)

for path in files:
    rows = playerboard.read_csv_rows(path)

    for raw in rows:
        raw_market = playerboard.first_value(raw, raw_market_keys)
        raw_label = playerboard.first_value(raw, ["side", "label", "title", "outcome", "outcome_name", "selection", "description"])
        raw_market_counts[raw_market or "<blank>"] += 1

        prop = playerboard.normalize_prop_row(raw, date_label)
        normalized_market_counts[prop.get("market") or "<blank>"] += 1

        haystack = " ".join([
            str(raw_market),
            str(raw_label),
            str(prop.get("market", "")),
            str(prop.get("marketDisplay", "")),
            str(prop.get("rawLabel", "")),
            str(prop.get("player", "")),
        ]).lower()

        if any(token in haystack for token in ["rbi", "runs batted", "stolen", "steal", "stolen base", "sb"]):
            possible_rows.append((path, raw_market, raw_label, prop, raw))

        if not prop.get("player") or not prop.get("market"):
            continue

        if prop["market"] not in market_set:
            rejected_market_counts[prop["market"]] += 1
            continue

        if date_label and playerboard.clean(prop.get("date")) and not playerboard.clean(prop.get("date")).startswith(date_label):
            continue

        if not playerboard.is_plausible_market_odds(prop.get("market"), prop.get("line"), prop.get("americanOdds")):
            rejected_plausibility_counts[prop["market"]] += 1
            continue

        kept_counts[prop["market"]] += 1

print("\n" + "=" * 100)
print("RAW MARKET COUNTS")
for k, v in raw_market_counts.most_common(100):
    print(f"{k:40s} {v}")

print("\n" + "=" * 100)
print("NORMALIZED MARKET COUNTS")
for k, v in normalized_market_counts.most_common(100):
    print(f"{k:40s} {v}")

print("\n" + "=" * 100)
print("KEPT COUNTS")
for k, v in kept_counts.most_common(100):
    print(f"{k:40s} {v}")

print("\n" + "=" * 100)
print("REJECTED BY MARKET COUNTS")
for k, v in rejected_market_counts.most_common(100):
    print(f"{k:40s} {v}")

print("\n" + "=" * 100)
print("REJECTED BY PLAUSIBILITY COUNTS")
for k, v in rejected_plausibility_counts.most_common(100):
    print(f"{k:40s} {v}")

print("\n" + "=" * 100)
print("POSSIBLE RBI/SB ROWS")
print("count:", len(possible_rows))
for path, raw_market, raw_label, prop, raw in possible_rows[:100]:
    print("\nSOURCE:", path)
    print("raw_market:", raw_market)
    print("raw_label:", raw_label)
    print("normalized:", prop)
    useful_raw = {k: raw.get(k) for k in raw.keys() if any(token in k.lower() for token in ["market", "type", "stat", "category", "label", "outcome", "player", "selection", "description", "line", "odds", "price"])}
    print("raw_useful:", useful_raw)
