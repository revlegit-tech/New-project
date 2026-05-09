from collections import Counter
from pathlib import Path

from mlb_app.services import playerboard_builder as playerboard

date_label = "2026-05-05"

raw_market_keys = [
    "market", "prop_market", "market_key", "marketKey", "type", "target",
    "stat", "category", "bet_type", "betType", "propType", "prop_type"
]

team_terms = [
    "team",
    "total runs",
    "runs",
    "first to score",
    "first team",
    "team to score",
    "race to",
    "moneyline",
    "game total",
]

raw_market_counts = Counter()
possible_team_rows = []

files = playerboard.saved_prop_files(date_label)

print("=" * 100)
print("SOURCE FILES")
for path in files:
    print(path)

for path in files:
    for raw in playerboard.read_csv_rows(path):
        raw_market = playerboard.first_value(raw, raw_market_keys)
        raw_label = playerboard.first_value(raw, [
            "side", "label", "title", "outcome", "outcome_name", "selection", "description"
        ])

        raw_market_counts[raw_market or "<blank>"] += 1

        haystack = " ".join(
            str(raw.get(k, "")) for k in raw.keys()
        ).lower()

        if any(term in haystack for term in team_terms):
            possible_team_rows.append((path, raw_market, raw_label, raw))

print("\n" + "=" * 100)
print("RAW MARKET COUNTS")
for k, v in raw_market_counts.most_common(100):
    print(f"{k:45s} {v}")

print("\n" + "=" * 100)
print("POSSIBLE TEAM PROP ROWS")
print("count:", len(possible_team_rows))

for path, raw_market, raw_label, raw in possible_team_rows[:100]:
    print("\nSOURCE:", path)
    print("raw_market:", raw_market)
    print("raw_label:", raw_label)
    useful = {
        k: raw.get(k)
        for k in raw.keys()
        if any(token in k.lower() for token in [
            "market", "type", "stat", "category", "label", "outcome",
            "team", "selection", "description", "line", "odds", "price",
            "player", "home", "away"
        ])
    }
    print("raw_useful:", useful)
